from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Decision,
    DecisionStatus,
    ProvenanceRecord,
    ProvenanceSubjectType,
    ProvenanceVerificationStatus,
)
from app.schemas import (
    DecisionReadinessItemRead,
    DecisionReadinessLevel,
    DecisionReadinessRead,
    DecisionReadinessSummaryRead,
)

RULE_VERSION = "decision-readiness-v1"
DUE_SOON_DAYS = 14
LEVEL_ORDER = {
    DecisionReadinessLevel.BLOCKED: 0,
    DecisionReadinessLevel.REVIEW: 1,
    DecisionReadinessLevel.WATCH: 2,
    DecisionReadinessLevel.READY: 3,
    DecisionReadinessLevel.CLOSED: 4,
}
SIGNAL_ORDER = {
    "decision_closed": 0,
    "expiration_overdue": 1,
    "rejected_evidence": 2,
    "missing_provenance": 3,
    "review_overdue": 4,
    "decision_proposed": 5,
    "unverified_evidence": 6,
    "observed_evidence": 7,
    "expires_soon": 8,
    "review_due_soon": 9,
    "verified_evidence": 10,
}
TERMINAL_STATUSES = {
    DecisionStatus.SUPERSEDED,
    DecisionStatus.EXPIRED,
    DecisionStatus.REVOKED,
}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_utc(value: datetime | None) -> datetime | None:
    return _as_utc(value) if value is not None else None


def _classify(
    decision: Decision,
    evidence_counts: Counter[str],
    current: datetime,
) -> tuple[DecisionReadinessLevel, str, list[str]]:
    status = DecisionStatus(decision.status)
    expires_at = _optional_utc(decision.expires_at)
    review_due_at = _optional_utc(decision.review_due_at)
    due_soon = current + timedelta(days=DUE_SOON_DAYS)
    total_evidence = sum(evidence_counts.values())

    if status in TERMINAL_STATUSES:
        return DecisionReadinessLevel.CLOSED, "decision_closed", ["decision_closed"]

    signals: list[str] = []
    if status == DecisionStatus.ACTIVE and expires_at is not None and expires_at <= current:
        signals.append("expiration_overdue")
    if evidence_counts[ProvenanceVerificationStatus.REJECTED.value]:
        signals.append("rejected_evidence")
    if total_evidence == 0:
        signals.append("missing_provenance")
    if review_due_at is not None and review_due_at <= current:
        signals.append("review_overdue")
    if status == DecisionStatus.PROPOSED:
        signals.append("decision_proposed")
    if evidence_counts[ProvenanceVerificationStatus.UNVERIFIED.value]:
        signals.append("unverified_evidence")
    if evidence_counts[ProvenanceVerificationStatus.OBSERVED.value]:
        signals.append("observed_evidence")
    if (
        status == DecisionStatus.ACTIVE
        and expires_at is not None
        and current < expires_at <= due_soon
    ):
        signals.append("expires_soon")
    if review_due_at is not None and current < review_due_at <= due_soon:
        signals.append("review_due_soon")
    if (
        total_evidence > 0
        and evidence_counts[ProvenanceVerificationStatus.VERIFIED.value] == total_evidence
    ):
        signals.append("verified_evidence")

    signals.sort(key=SIGNAL_ORDER.__getitem__)
    primary = signals[0]
    if primary in {"expiration_overdue", "rejected_evidence", "missing_provenance"}:
        level = DecisionReadinessLevel.BLOCKED
    elif primary in {"review_overdue", "decision_proposed", "unverified_evidence"}:
        level = DecisionReadinessLevel.REVIEW
    elif primary in {"observed_evidence", "expires_soon", "review_due_soon"}:
        level = DecisionReadinessLevel.WATCH
    else:
        level = DecisionReadinessLevel.READY
    return level, primary, signals


def _sort_key(item: DecisionReadinessItemRead) -> tuple[object, ...]:
    deadline = min(
        (value for value in (item.review_due_at, item.expires_at) if value is not None),
        default=datetime.max.replace(tzinfo=UTC),
    )
    return (
        LEVEL_ORDER[item.readiness_level],
        deadline,
        item.effective_at,
        item.id,
    )


async def build_decision_readiness(
    session: AsyncSession,
    tenant_id: str,
    *,
    include_ready: bool = False,
    include_closed: bool = False,
    limit: int = 100,
    now: datetime | None = None,
) -> DecisionReadinessRead:
    """Build a deterministic, tenant-safe readiness queue without writes or AI calls."""

    current = _as_utc(now or datetime.now(UTC))
    decisions = list(await session.scalars(select(Decision).where(Decision.tenant_id == tenant_id)))
    evidence = list(
        await session.scalars(
            select(ProvenanceRecord).where(
                ProvenanceRecord.tenant_id == tenant_id,
                ProvenanceRecord.subject_type == ProvenanceSubjectType.DECISION,
            )
        )
    )
    evidence_by_decision: dict[str, Counter[str]] = defaultdict(Counter)
    for record in evidence:
        if record.decision_id is not None:
            evidence_by_decision[record.decision_id][str(record.verification_status)] += 1

    items: list[DecisionReadinessItemRead] = []
    for decision in decisions:
        counts = evidence_by_decision[decision.id]
        normalized_counts = {
            status.value: counts[status.value] for status in ProvenanceVerificationStatus
        }
        level, reason, signals = _classify(decision, counts, current)
        items.append(
            DecisionReadinessItemRead(
                id=decision.id,
                subject=decision.subject,
                choice=decision.choice,
                status=DecisionStatus(decision.status),
                scope=decision.scope,
                applies_to=decision.applies_to or {},
                readiness_level=level,
                readiness_reason=reason,
                signals=signals,
                evidence_counts=normalized_counts,
                total_evidence=sum(normalized_counts.values()),
                effective_at=_as_utc(decision.effective_at),
                expires_at=_optional_utc(decision.expires_at),
                review_due_at=_optional_utc(decision.review_due_at),
            )
        )

    readiness_counts = {
        level.value: sum(1 for item in items if item.readiness_level == level)
        for level in DecisionReadinessLevel
    }
    summary = DecisionReadinessSummaryRead(
        total_decisions=len(items),
        active_decisions=sum(1 for item in items if item.status == DecisionStatus.ACTIVE),
        proposed_decisions=sum(1 for item in items if item.status == DecisionStatus.PROPOSED),
        ready_decisions=readiness_counts[DecisionReadinessLevel.READY.value],
        watch_decisions=readiness_counts[DecisionReadinessLevel.WATCH.value],
        review_decisions=readiness_counts[DecisionReadinessLevel.REVIEW.value],
        blocked_decisions=readiness_counts[DecisionReadinessLevel.BLOCKED.value],
        closed_decisions=readiness_counts[DecisionReadinessLevel.CLOSED.value],
        readiness_counts=readiness_counts,
    )

    selected = [
        item
        for item in items
        if (include_ready or item.readiness_level != DecisionReadinessLevel.READY)
        and (include_closed or item.readiness_level != DecisionReadinessLevel.CLOSED)
    ]
    selected.sort(key=_sort_key)
    return DecisionReadinessRead(
        rule_version=RULE_VERSION,
        generated_at=current,
        summary=summary,
        items=selected[:limit],
    )
