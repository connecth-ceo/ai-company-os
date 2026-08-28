from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import (
    Approval,
    ApprovalStatus,
    AttentionKind,
    AttentionLevel,
    Commitment,
    CommitmentStatus,
    Task,
    TaskRun,
    TaskStatus,
)
from app.schemas import AttentionItemRead, AttentionQueueRead

RULE_VERSION = "attention-rules-v1"
LEVEL_ORDER = {
    AttentionLevel.INFO: 0,
    AttentionLevel.WATCH: 1,
    AttentionLevel.ACTION: 2,
    AttentionLevel.DECISION: 3,
    AttentionLevel.CRITICAL: 4,
}


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _age_seconds(current: datetime, detected_at: datetime) -> int:
    return max(0, int((current - as_utc(detected_at)).total_seconds()))


def _item_id(kind: AttentionKind, resource_id: str) -> str:
    return f"{kind.value}:{resource_id}"


async def build_attention_queue(
    session: AsyncSession,
    tenant_id: str,
    *,
    settings: Settings,
    now: datetime | None = None,
    minimum_level: AttentionLevel = AttentionLevel.INFO,
    kind: AttentionKind | None = None,
    limit: int = 100,
) -> AttentionQueueRead:
    """Compute a read-only CEO attention queue without an AI call or side effect."""

    current = as_utc(now or datetime.now(UTC))
    items: list[AttentionItemRead] = []

    commitments = list(
        await session.scalars(
            select(Commitment).where(
                Commitment.tenant_id == tenant_id,
                Commitment.status.in_(
                    [CommitmentStatus.OPEN, CommitmentStatus.IN_PROGRESS]
                ),
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
                    "작업자 로그와 실행 상태를 확인하고, 중복 실행 전에 복구 여부를 "
                    "결정해 주세요."
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
    counts = {
        level.value: sum(1 for item in selected if item.level == level)
        for level in AttentionLevel
    }
    return AttentionQueueRead(
        rule_version=RULE_VERSION,
        generated_at=current,
        total=len(selected),
        counts=counts,
        items=selected[:limit],
    )
