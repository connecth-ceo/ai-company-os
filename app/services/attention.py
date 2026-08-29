import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import (
    Approval,
    ApprovalStatus,
    AttentionAcknowledgement,
    AttentionKind,
    AttentionLevel,
    Commitment,
    CommitmentStatus,
    Task,
    TaskRun,
    TaskStatus,
)
from app.schemas import (
    AttentionItemRead,
    AttentionQueueRead,
    DecisionFollowThroughItemRead,
    DecisionFollowThroughLevel,
    DecisionReadinessItemRead,
    DecisionReadinessLevel,
)
from app.services.decision_follow_through import build_decision_follow_through
from app.services.decision_readiness import build_decision_readiness

RULE_VERSION = "attention-rules-v3"
LEVEL_ORDER = {
    AttentionLevel.INFO: 0,
    AttentionLevel.WATCH: 1,
    AttentionLevel.ACTION: 2,
    AttentionLevel.DECISION: 3,
    AttentionLevel.CRITICAL: 4,
}
VOLATILE_EVIDENCE_KEYS = {
    "overdue_seconds",
    "pending_seconds",
    "running_seconds",
}


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _age_seconds(current: datetime, detected_at: datetime) -> int:
    return max(0, int((current - as_utc(detected_at)).total_seconds()))


def _item_id(kind: AttentionKind, resource_id: str) -> str:
    return f"{kind.value}:{resource_id}"


def attention_fingerprint(item: AttentionItemRead) -> str:
    """Hash stable signal state while ignoring counters that change every request."""

    stable_evidence = {
        key: value for key, value in item.evidence.items() if key not in VOLATILE_EVIDENCE_KEYS
    }
    payload = {
        "id": item.id,
        "level": item.level.value,
        "kind": item.kind.value,
        "resource_type": item.resource_type,
        "resource_id": item.resource_id,
        "project_id": item.project_id,
        "detected_at": as_utc(item.detected_at).isoformat(),
        "evidence": stable_evidence,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _decision_detected_at(
    readiness: DecisionReadinessItemRead,
    follow_through: DecisionFollowThroughItemRead | None,
) -> datetime:
    if readiness.readiness_reason == "expiration_overdue" and readiness.expires_at:
        return as_utc(readiness.expires_at)
    if readiness.readiness_reason == "review_overdue" and readiness.review_due_at:
        return as_utc(readiness.review_due_at)
    if (
        follow_through is not None
        and follow_through.follow_through_level == DecisionFollowThroughLevel.AT_RISK
        and follow_through.next_due_at is not None
    ):
        return as_utc(follow_through.next_due_at)
    return as_utc(readiness.effective_at)


def _decision_recommendation(
    readiness: DecisionReadinessItemRead,
    follow_through: DecisionFollowThroughItemRead | None,
) -> str:
    if readiness.readiness_level == DecisionReadinessLevel.BLOCKED:
        return "근거와 유효기간을 확인한 뒤 결정의 유지·정정·철회 여부를 판단해 주세요."
    if (
        follow_through is not None
        and follow_through.follow_through_level == DecisionFollowThroughLevel.AT_RISK
    ):
        return "지연되거나 취소된 후속조치의 담당자·기한·대체 행동을 결정해 주세요."
    if readiness.readiness_level == DecisionReadinessLevel.REVIEW:
        return "제안 상태나 미검증 근거를 검토해 결정의 효력을 확인해 주세요."
    if (
        follow_through is not None
        and follow_through.follow_through_level == DecisionFollowThroughLevel.UNTRACKED
    ):
        return "이 결정을 실행할 담당자와 마감일이 있는 후속 약속을 연결해 주세요."
    return "재검토일·만료일 또는 관찰 근거를 확인해 주세요."


def _decision_level(
    readiness: DecisionReadinessItemRead,
    follow_through: DecisionFollowThroughItemRead | None,
) -> AttentionLevel | None:
    candidates: list[AttentionLevel] = []
    readiness_levels = {
        DecisionReadinessLevel.BLOCKED: AttentionLevel.CRITICAL,
        DecisionReadinessLevel.REVIEW: AttentionLevel.DECISION,
        DecisionReadinessLevel.WATCH: AttentionLevel.WATCH,
    }
    follow_through_levels = {
        DecisionFollowThroughLevel.AT_RISK: AttentionLevel.DECISION,
        DecisionFollowThroughLevel.UNTRACKED: AttentionLevel.ACTION,
    }
    readiness_level = readiness_levels.get(readiness.readiness_level)
    if readiness_level is not None:
        candidates.append(readiness_level)
    if follow_through is not None:
        follow_through_level = follow_through_levels.get(follow_through.follow_through_level)
        if follow_through_level is not None:
            candidates.append(follow_through_level)
    return max(candidates, key=LEVEL_ORDER.__getitem__) if candidates else None


async def build_attention_queue(
    session: AsyncSession,
    tenant_id: str,
    *,
    settings: Settings,
    now: datetime | None = None,
    minimum_level: AttentionLevel = AttentionLevel.INFO,
    kind: AttentionKind | None = None,
    include_acknowledged: bool = True,
    limit: int | None = 100,
) -> AttentionQueueRead:
    """Compute a read-only CEO attention queue without an AI call or side effect."""

    current = as_utc(now or datetime.now(UTC))
    items: list[AttentionItemRead] = []

    commitments = list(
        await session.scalars(
            select(Commitment).where(
                Commitment.tenant_id == tenant_id,
                Commitment.status.in_([CommitmentStatus.OPEN, CommitmentStatus.IN_PROGRESS]),
                Commitment.due_at < current,
            )
        )
    )
    for commitment in commitments:
        detected_at = as_utc(commitment.due_at)
        age = _age_seconds(current, detected_at)
        overdue_hours = age / 3_600
        if overdue_hours >= settings.attention_commitment_critical_hours:
            level = AttentionLevel.CRITICAL
        elif overdue_hours >= settings.attention_commitment_decision_hours:
            level = AttentionLevel.DECISION
        else:
            level = AttentionLevel.ACTION
        items.append(
            AttentionItemRead(
                id=_item_id(AttentionKind.OVERDUE_COMMITMENT, commitment.id),
                level=level,
                kind=AttentionKind.OVERDUE_COMMITMENT,
                title="기한을 넘긴 약속",
                summary=commitment.statement,
                recommendation="담당자와 다음 행동을 확인해 주세요.",
                resource_type="commitment",
                resource_id=commitment.id,
                project_id=commitment.project_id,
                detected_at=detected_at,
                age_seconds=age,
                evidence={
                    "owner_type": str(commitment.owner_type),
                    "owner_id": commitment.owner_id,
                    "due_at": detected_at.isoformat(),
                    "overdue_seconds": age,
                },
            )
        )

    running_tasks = list(
        await session.scalars(
            select(Task).where(
                Task.tenant_id == tenant_id,
                Task.status == TaskStatus.RUNNING,
            )
        )
    )
    for task in running_tasks:
        detected_at = as_utc(task.updated_at)
        age = _age_seconds(current, detected_at)
        if age < settings.attention_task_stale_seconds:
            continue
        level = (
            AttentionLevel.CRITICAL
            if age >= settings.attention_task_stale_seconds * 2
            else AttentionLevel.ACTION
        )
        items.append(
            AttentionItemRead(
                id=_item_id(AttentionKind.LONG_RUNNING_TASK, task.id),
                level=level,
                kind=AttentionKind.LONG_RUNNING_TASK,
                title="오래 실행 중인 업무",
                summary=task.title,
                recommendation=(
                    "작업자 로그와 실행 상태를 확인하고, 중복 실행 전에 복구 여부를 결정해 주세요."
                ),
                resource_type="task",
                resource_id=task.id,
                project_id=task.project_id,
                detected_at=detected_at,
                age_seconds=age,
                evidence={
                    "status": str(task.status),
                    "running_seconds": age,
                    "stale_threshold_seconds": settings.attention_task_stale_seconds,
                },
            )
        )

    failed_run_counts = (
        select(
            TaskRun.task_id.label("task_id"),
            func.count(TaskRun.id).label("failure_count"),
            func.max(TaskRun.finished_at).label("last_failure_at"),
        )
        .where(TaskRun.status == TaskStatus.FAILED)
        .group_by(TaskRun.task_id)
        .subquery()
    )
    failed_rows = (
        await session.execute(
            select(
                Task,
                func.coalesce(failed_run_counts.c.failure_count, 0),
                failed_run_counts.c.last_failure_at,
            )
            .outerjoin(failed_run_counts, failed_run_counts.c.task_id == Task.id)
            .where(
                Task.tenant_id == tenant_id,
                Task.status == TaskStatus.FAILED,
            )
        )
    ).all()
    for task, recorded_failures, last_failure_at in failed_rows:
        failure_count = max(1, int(recorded_failures or 0))
        if failure_count >= 3:
            level = AttentionLevel.CRITICAL
        elif failure_count >= 2:
            level = AttentionLevel.DECISION
        else:
            level = AttentionLevel.WATCH
        detected_at = as_utc(last_failure_at or task.updated_at)
        age = _age_seconds(current, detected_at)
        items.append(
            AttentionItemRead(
                id=_item_id(AttentionKind.TASK_FAILURE, task.id),
                level=level,
                kind=AttentionKind.TASK_FAILURE,
                title=("반복 실패한 업무" if failure_count >= 2 else "실패한 업무"),
                summary=task.title,
                recommendation=(
                    "자동 재시도 전에 실패 원인과 비용 중복 가능성을 검토해 주세요."
                    if failure_count >= 2
                    else "오류 내용을 확인하고 재시도 필요성을 판단해 주세요."
                ),
                resource_type="task",
                resource_id=task.id,
                project_id=task.project_id,
                detected_at=detected_at,
                age_seconds=age,
                evidence={
                    "failure_count": failure_count,
                    "error": (task.error or "")[:500],
                },
            )
        )

    approvals = list(
        await session.scalars(
            select(Approval).where(
                Approval.tenant_id == tenant_id,
                Approval.status == ApprovalStatus.PENDING,
            )
        )
    )
    for approval in approvals:
        detected_at = as_utc(approval.created_at)
        age = _age_seconds(current, detected_at)
        level = (
            AttentionLevel.CRITICAL
            if approval.risk == "critical"
            or age >= settings.attention_approval_critical_hours * 3_600
            else AttentionLevel.DECISION
        )
        items.append(
            AttentionItemRead(
                id=_item_id(AttentionKind.PENDING_APPROVAL, approval.id),
                level=level,
                kind=AttentionKind.PENDING_APPROVAL,
                title="대표 승인 대기",
                summary=approval.action,
                recommendation="승인 또는 거절 결정을 내려 주세요.",
                resource_type="approval",
                resource_id=approval.id,
                project_id=None,
                detected_at=detected_at,
                age_seconds=age,
                evidence={
                    "risk": approval.risk,
                    "reason": approval.reason[:500],
                    "task_id": approval.task_id,
                    "pending_seconds": age,
                },
            )
        )

    readiness_queue = await build_decision_readiness(
        session,
        tenant_id,
        include_ready=True,
        include_closed=True,
        limit=None,
        now=current,
    )
    follow_through_queue = await build_decision_follow_through(
        session,
        tenant_id,
        include_complete=True,
        include_inactive=True,
        limit=None,
        now=current,
    )
    follow_through_by_id = {item.id: item for item in follow_through_queue.items}
    for readiness in readiness_queue.items:
        follow_through = follow_through_by_id.get(readiness.id)
        level = _decision_level(readiness, follow_through)
        if level is None:
            continue
        detected_at = _decision_detected_at(readiness, follow_through)
        follow_level = (
            follow_through.follow_through_level.value if follow_through is not None else None
        )
        follow_reason = follow_through.follow_through_reason if follow_through is not None else None
        items.append(
            AttentionItemRead(
                id=_item_id(AttentionKind.DECISION_GOVERNANCE, readiness.id),
                level=level,
                kind=AttentionKind.DECISION_GOVERNANCE,
                title="대표 결정 확인",
                summary=f"{readiness.subject}: {readiness.choice}"[:1_000],
                recommendation=_decision_recommendation(readiness, follow_through),
                resource_type="decision",
                resource_id=readiness.id,
                project_id=readiness.applies_to.get("project_id"),
                detected_at=detected_at,
                age_seconds=_age_seconds(current, detected_at),
                evidence={
                    "readiness_level": readiness.readiness_level.value,
                    "readiness_reason": readiness.readiness_reason,
                    "readiness_signals": ",".join(readiness.signals),
                    "follow_through_level": follow_level,
                    "follow_through_reason": follow_reason,
                    "total_evidence": readiness.total_evidence,
                    "total_commitments": (
                        follow_through.total_commitments if follow_through is not None else 0
                    ),
                    "overdue_commitments": (
                        follow_through.overdue_commitments if follow_through is not None else 0
                    ),
                },
            )
        )

    selected = [
        item
        for item in items
        if LEVEL_ORDER[item.level] >= LEVEL_ORDER[minimum_level]
        and (kind is None or item.kind == kind)
    ]
    selected.sort(
        key=lambda item: (
            -LEVEL_ORDER[item.level],
            -item.age_seconds,
            item.kind.value,
            item.resource_id,
        )
    )
    selected = [
        item.model_copy(update={"fingerprint": attention_fingerprint(item)}) for item in selected
    ]
    acknowledgements = []
    if selected:
        attention_ids = [item.id for item in selected]
        acknowledgements = list(
            await session.scalars(
                select(AttentionAcknowledgement).where(
                    AttentionAcknowledgement.tenant_id == tenant_id,
                    AttentionAcknowledgement.attention_id.in_(attention_ids),
                )
            )
        )
    acknowledgement_by_signal = {
        (item.attention_id, item.fingerprint): item for item in acknowledgements
    }
    selected = [
        item.model_copy(
            update={
                "acknowledged": acknowledgement is not None,
                "acknowledgement_id": acknowledgement.id if acknowledgement else None,
                "acknowledged_at": acknowledgement.created_at if acknowledgement else None,
                "acknowledged_by": (acknowledgement.acknowledged_by if acknowledgement else None),
            }
        )
        for item in selected
        for acknowledgement in [acknowledgement_by_signal.get((item.id, item.fingerprint))]
    ]
    acknowledged_total = sum(1 for item in selected if item.acknowledged)
    unacknowledged_total = len(selected) - acknowledged_total
    unacknowledged_counts = {
        level.value: sum(1 for item in selected if item.level == level and not item.acknowledged)
        for level in AttentionLevel
    }
    if not include_acknowledged:
        selected = [item for item in selected if not item.acknowledged]
    counts = {
        level.value: sum(1 for item in selected if item.level == level) for level in AttentionLevel
    }
    return AttentionQueueRead(
        rule_version=RULE_VERSION,
        generated_at=current,
        total=len(selected),
        counts=counts,
        unacknowledged_counts=unacknowledged_counts,
        acknowledged_total=acknowledged_total,
        unacknowledged_total=unacknowledged_total,
        items=selected if limit is None else selected[:limit],
    )
