from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Commitment,
    CommitmentSourceType,
    CommitmentStatus,
    Decision,
    Project,
    Task,
)
from app.schemas import CommitmentCreate, CommitmentTransition
from app.services.audit import add_audit_event


class CommitmentLifecycleRejected(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _bounded_metadata(name: str, values: dict[str, str]) -> dict[str, str]:
    normalized = {str(key).strip(): str(value).strip() for key, value in values.items()}
    if len(normalized) > 20 or any(
        not key or not value or len(key) > 80 or len(value) > 1_000
        for key, value in normalized.items()
    ):
        raise CommitmentLifecycleRejected(
            f"invalid_{name}",
            f"{name} must contain at most 20 non-empty, bounded text fields",
        )
    return normalized


async def _require_links(
    session: AsyncSession,
    *,
    tenant_id: str,
    project_id: str | None,
    task_id: str | None,
    decision_id: str | None,
) -> tuple[Project | None, Task | None, Decision | None]:
    project = None
    task = None
    decision = None
    if project_id:
        project = await session.scalar(
            select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id)
        )
        if project is None:
            raise CommitmentLifecycleRejected("project_not_found", "Related project not found")
    if task_id:
        task = await session.scalar(
            select(Task).where(Task.id == task_id, Task.tenant_id == tenant_id)
        )
        if task is None:
            raise CommitmentLifecycleRejected("task_not_found", "Related task not found")
        if project_id and task.project_id != project_id:
            raise CommitmentLifecycleRejected(
                "project_task_mismatch",
                "Related task must belong to the related project",
            )
    if decision_id:
        decision = await session.scalar(
            select(Decision).where(
                Decision.id == decision_id,
                Decision.tenant_id == tenant_id,
            )
        )
        if decision is None:
            raise CommitmentLifecycleRejected(
                "decision_not_found", "Related decision not found"
            )
    return project, task, decision


def _normalize_source(
    *,
    source_type: CommitmentSourceType,
    source_id: str | None,
    task_id: str | None,
    decision_id: str | None,
) -> str | None:
    normalized = source_id.strip() if source_id else None
    if source_type == CommitmentSourceType.MANUAL and normalized:
        raise CommitmentLifecycleRejected(
            "invalid_manual_source", "Manual commitments cannot have a source_id"
        )
    if source_type == CommitmentSourceType.TASK:
        if not task_id or normalized not in {None, task_id}:
            raise CommitmentLifecycleRejected(
                "invalid_task_source", "Task source must reference the related task"
            )
        return task_id
    if source_type == CommitmentSourceType.DECISION:
        if not decision_id or normalized not in {None, decision_id}:
            raise CommitmentLifecycleRejected(
                "invalid_decision_source",
                "Decision source must reference the related decision",
            )
        return decision_id
    if source_type in {CommitmentSourceType.MEETING, CommitmentSourceType.EXTERNAL}:
        if not normalized:
            raise CommitmentLifecycleRejected(
                "source_id_required",
                f"{source_type.value} commitments require a source_id",
            )
    return normalized


async def create_commitment(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor: str,
    payload: CommitmentCreate,
) -> Commitment:
    if payload.status not in {CommitmentStatus.OPEN, CommitmentStatus.IN_PROGRESS}:
        raise CommitmentLifecycleRejected(
            "invalid_initial_status",
            "A commitment can only be created as open or in_progress",
        )
    statement = payload.statement.strip()
    owner_id = payload.owner_id.strip()
    if not statement or not owner_id:
        raise CommitmentLifecycleRejected(
            "blank_required_field",
            "Commitment statement and owner_id must contain visible text",
        )
    await _require_links(
        session,
        tenant_id=tenant_id,
        project_id=payload.project_id,
        task_id=payload.task_id,
        decision_id=payload.decision_id,
    )
    source_id = _normalize_source(
        source_type=payload.source_type,
        source_id=payload.source_id,
        task_id=payload.task_id,
        decision_id=payload.decision_id,
    )
    provenance = _bounded_metadata("provenance", payload.provenance)
    reminder_policy = _bounded_metadata("reminder_policy", payload.reminder_policy)
    values = payload.model_dump(
        exclude={
            "statement",
            "owner_id",
            "due_at",
            "source_id",
            "provenance",
            "reminder_policy",
        }
    )
    item = Commitment(
        tenant_id=tenant_id,
        **values,
        statement=statement,
        owner_id=owner_id,
        due_at=as_utc(payload.due_at),
        source_id=source_id,
        provenance=provenance,
        reminder_policy=reminder_policy,
    )
    session.add(item)
    await session.flush()
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="commitment.created",
        resource_type="commitment",
        resource_id=item.id,
        details={
            "owner_type": item.owner_type.value,
            "owner_id": item.owner_id,
            "due_at": item.due_at.isoformat(),
            "decision_id": item.decision_id,
            "project_id": item.project_id,
            "task_id": item.task_id,
        },
    )
    return item


async def transition_commitment(
    session: AsyncSession,
    *,
    item: Commitment,
    tenant_id: str,
    actor: str,
    payload: CommitmentTransition,
) -> Commitment:
    current = CommitmentStatus(item.status)
    target = payload.status
    allowed: dict[CommitmentStatus, set[CommitmentStatus]] = {
        CommitmentStatus.OPEN: {
            CommitmentStatus.IN_PROGRESS,
            CommitmentStatus.COMPLETED,
            CommitmentStatus.CANCELLED,
        },
        CommitmentStatus.IN_PROGRESS: {
            CommitmentStatus.OPEN,
            CommitmentStatus.COMPLETED,
            CommitmentStatus.CANCELLED,
        },
        CommitmentStatus.COMPLETED: set(),
        CommitmentStatus.CANCELLED: set(),
    }
    if target not in allowed[current]:
        raise CommitmentLifecycleRejected(
            "invalid_status_transition",
            f"Commitment status cannot change from {current.value} to {target.value}",
        )
    item.status = target
    item.completed_at = datetime.now(UTC) if target == CommitmentStatus.COMPLETED else None
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action=f"commitment.{target.value}",
        resource_type="commitment",
        resource_id=item.id,
        details={"previous_status": current.value, "note": payload.note},
    )
    return item
