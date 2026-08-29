from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Commitment, CommitmentStatus, Decision, DecisionStatus
from app.schemas import (
    DecisionFollowThroughItemRead,
    DecisionFollowThroughLevel,
    DecisionFollowThroughRead,
    DecisionFollowThroughSummaryRead,
)

RULE_VERSION = "decision-follow-through-v1"
LEVEL_ORDER = {
    DecisionFollowThroughLevel.AT_RISK: 0,
    DecisionFollowThroughLevel.UNTRACKED: 1,
    DecisionFollowThroughLevel.IN_PROGRESS: 2,
    DecisionFollowThroughLevel.PLANNED: 3,
    DecisionFollowThroughLevel.COMPLETE: 4,
    DecisionFollowThroughLevel.INACTIVE: 5,
}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _classify(
    decision: Decision,
    linked: list[Commitment],
    current: datetime,
) -> tuple[DecisionFollowThroughLevel, str, int, datetime | None]:
    if DecisionStatus(decision.status) != DecisionStatus.ACTIVE:
        return DecisionFollowThroughLevel.INACTIVE, "decision_not_active", 0, None
    if not linked:
        return DecisionFollowThroughLevel.UNTRACKED, "no_commitment", 0, None

    active = [
        item
        for item in linked
        if CommitmentStatus(item.status) in {CommitmentStatus.OPEN, CommitmentStatus.IN_PROGRESS}
    ]
    overdue = sum(1 for item in active if _as_utc(item.due_at) < current)
    next_due_at = min((_as_utc(item.due_at) for item in active), default=None)
    counts = Counter(str(item.status) for item in linked)

    if overdue:
        return DecisionFollowThroughLevel.AT_RISK, "overdue_commitment", overdue, next_due_at
    if counts[CommitmentStatus.CANCELLED.value] == len(linked):
        return DecisionFollowThroughLevel.AT_RISK, "cancelled_only", 0, None
    if counts[CommitmentStatus.IN_PROGRESS.value]:
        return DecisionFollowThroughLevel.IN_PROGRESS, "commitment_in_progress", 0, next_due_at
    if counts[CommitmentStatus.OPEN.value]:
        return DecisionFollowThroughLevel.PLANNED, "commitment_planned", 0, next_due_at
    return DecisionFollowThroughLevel.COMPLETE, "commitments_complete", 0, None


def _sort_key(item: DecisionFollowThroughItemRead) -> tuple[object, ...]:
    return (
        LEVEL_ORDER[item.follow_through_level],
        item.next_due_at or datetime.max.replace(tzinfo=UTC),
        item.effective_at,
        item.id,
    )


async def build_decision_follow_through(
    session: AsyncSession,
    tenant_id: str,
    *,
    include_complete: bool = False,
    include_inactive: bool = False,
    limit: int = 100,
    now: datetime | None = None,
) -> DecisionFollowThroughRead:
    """Build a deterministic execution-link queue without writes or AI calls."""

    current = _as_utc(now or datetime.now(UTC))
    decisions = list(await session.scalars(select(Decision).where(Decision.tenant_id == tenant_id)))
    commitments = list(
        await session.scalars(select(Commitment).where(Commitment.tenant_id == tenant_id))
    )
    commitments_by_decision: dict[str, list[Commitment]] = defaultdict(list)
    for commitment in commitments:
        if commitment.decision_id is not None:
            commitments_by_decision[commitment.decision_id].append(commitment)

    items: list[DecisionFollowThroughItemRead] = []
    for decision in decisions:
        linked = commitments_by_decision[decision.id]
        counts = {status.value: 0 for status in CommitmentStatus}
        for commitment in linked:
            counts[str(commitment.status)] += 1
        level, reason, overdue, next_due_at = _classify(decision, linked, current)
        items.append(
            DecisionFollowThroughItemRead(
                id=decision.id,
                subject=decision.subject,
                choice=decision.choice,
                status=DecisionStatus(decision.status),
                follow_through_level=level,
                follow_through_reason=reason,
                commitment_counts=counts,
                total_commitments=len(linked),
                overdue_commitments=overdue,
                next_due_at=next_due_at,
                effective_at=_as_utc(decision.effective_at),
            )
        )

    active_items = [item for item in items if item.status == DecisionStatus.ACTIVE]
    linked_decisions = sum(1 for item in active_items if item.total_commitments > 0)
    level_counts = {
        level.value: sum(1 for item in items if item.follow_through_level == level)
        for level in DecisionFollowThroughLevel
    }
    summary = DecisionFollowThroughSummaryRead(
        total_decisions=len(items),
        active_decisions=len(active_items),
        linked_decisions=linked_decisions,
        execution_coverage_percent=(
            round(linked_decisions * 100 / len(active_items)) if active_items else 0
        ),
        untracked_decisions=level_counts[DecisionFollowThroughLevel.UNTRACKED.value],
        at_risk_decisions=level_counts[DecisionFollowThroughLevel.AT_RISK.value],
        planned_decisions=level_counts[DecisionFollowThroughLevel.PLANNED.value],
        in_progress_decisions=level_counts[DecisionFollowThroughLevel.IN_PROGRESS.value],
        complete_decisions=level_counts[DecisionFollowThroughLevel.COMPLETE.value],
        inactive_decisions=level_counts[DecisionFollowThroughLevel.INACTIVE.value],
        follow_through_counts=level_counts,
    )
    selected = [
        item
        for item in items
        if (include_complete or item.follow_through_level != DecisionFollowThroughLevel.COMPLETE)
        and (include_inactive or item.follow_through_level != DecisionFollowThroughLevel.INACTIVE)
    ]
    selected.sort(key=_sort_key)
    return DecisionFollowThroughRead(
        rule_version=RULE_VERSION,
        generated_at=current,
        summary=summary,
        items=selected[:limit],
    )
