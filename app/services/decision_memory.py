from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Decision, DecisionScope, DecisionStatus, Project, Task
from app.schemas import DecisionCreate, DecisionTransition
from app.services.audit import add_audit_event
from app.services.provenance import capture_decision_provenance


class DecisionLifecycleRejected(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _require_scoped_resource(
    session: AsyncSession,
    *,
    tenant_id: str,
    scope: DecisionScope,
    applies_to: dict[str, str],
) -> dict[str, str]:
    normalized = {key: value.strip() for key, value in applies_to.items()}
    if any(
        not key or not value or len(key) > 80 or len(value) > 240
        for key, value in normalized.items()
    ):
        raise DecisionLifecycleRejected(
            "invalid_scope_target",
            "Decision scope target keys and values must be non-empty and bounded",
        )

    expected_keys: dict[DecisionScope, set[str]] = {
        DecisionScope.COMPANY: set(),
        DecisionScope.PROJECT: {"project_id"},
        DecisionScope.TASK: {"task_id"},
        DecisionScope.DEPARTMENT: {"department"},
    }
    if set(normalized) != expected_keys[scope]:
        expected = ", ".join(sorted(expected_keys[scope])) or "no fields"
        raise DecisionLifecycleRejected(
            "invalid_scope_target",
            f"{scope.value} scope requires exactly: {expected}",
        )

    if scope == DecisionScope.PROJECT:
        project = await session.scalar(
            select(Project).where(
                Project.id == normalized["project_id"],
                Project.tenant_id == tenant_id,
            )
        )
        if project is None:
            raise DecisionLifecycleRejected(
                "scope_target_not_found",
                "Scoped project not found",
            )
    elif scope == DecisionScope.TASK:
        task = await session.scalar(
            select(Task).where(
                Task.id == normalized["task_id"],
                Task.tenant_id == tenant_id,
            )
        )
        if task is None:
            raise DecisionLifecycleRejected(
                "scope_target_not_found",
                "Scoped task not found",
            )
    return normalized


async def create_decision(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor: str,
    payload: DecisionCreate,
) -> Decision:
    if payload.status not in {DecisionStatus.PROPOSED, DecisionStatus.ACTIVE}:
        raise DecisionLifecycleRejected(
            "invalid_initial_status",
            "A decision can only be created as proposed or active",
        )

    if payload.task_id:
        source_task = await session.scalar(
            select(Task).where(
                Task.id == payload.task_id,
                Task.tenant_id == tenant_id,
            )
        )
        if source_task is None:
            raise DecisionLifecycleRejected("source_task_not_found", "Source task not found")

    applies_to = await _require_scoped_resource(
        session,
        tenant_id=tenant_id,
        scope=payload.scope,
        applies_to=payload.applies_to,
    )
    effective_at = as_utc(payload.effective_at or datetime.now(UTC))
    expires_at = as_utc(payload.expires_at) if payload.expires_at else None
    review_due_at = as_utc(payload.review_due_at) if payload.review_due_at else None
    if expires_at and expires_at <= effective_at:
        raise DecisionLifecycleRejected(
            "invalid_expiration",
            "expires_at must be later than effective_at",
        )
    if review_due_at and review_due_at <= effective_at:
        raise DecisionLifecycleRejected(
            "invalid_review_due",
            "review_due_at must be later than effective_at",
        )

    superseded: Decision | None = None
    if payload.supersedes_decision_id:
        if payload.status != DecisionStatus.ACTIVE:
            raise DecisionLifecycleRejected(
                "replacement_not_active",
                "A replacement decision must be active",
            )
        superseded = await session.scalar(
            select(Decision)
            .where(
                Decision.id == payload.supersedes_decision_id,
                Decision.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if superseded is None:
            raise DecisionLifecycleRejected(
                "superseded_decision_not_found",
                "Decision to supersede not found",
            )
        if superseded.status != DecisionStatus.ACTIVE:
            raise DecisionLifecycleRejected(
                "superseded_decision_not_active",
                "Only an active decision can be superseded",
            )
        if superseded.scope != payload.scope or superseded.applies_to != applies_to:
            raise DecisionLifecycleRejected(
                "replacement_scope_mismatch",
                "Replacement decision must keep the same scope and target",
            )

    values = payload.model_dump(
        exclude={"effective_at", "expires_at", "review_due_at", "applies_to"}
    )
    item = Decision(
        tenant_id=tenant_id,
        **values,
        applies_to=applies_to,
        effective_at=effective_at,
        expires_at=expires_at,
        review_due_at=review_due_at,
    )
    session.add(item)
    await session.flush()

    if superseded:
        superseded.status = DecisionStatus.SUPERSEDED
        add_audit_event(
            session,
            tenant_id=tenant_id,
            actor=actor,
            action="decision.superseded",
            resource_type="decision",
            resource_id=superseded.id,
            details={"replacement_decision_id": item.id},
        )
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="decision.created",
        resource_type="decision",
        resource_id=item.id,
        details={
            "status": item.status.value,
            "scope": item.scope.value,
            "supersedes_decision_id": item.supersedes_decision_id,
        },
    )
    await capture_decision_provenance(
        session,
        tenant_id=tenant_id,
        decision=item,
        actor=actor,
    )
    return item


async def transition_decision(
    session: AsyncSession,
    *,
    item: Decision,
    tenant_id: str,
    actor: str,
    payload: DecisionTransition,
) -> Decision:
    current = DecisionStatus(item.status)
    target = payload.status
    allowed: dict[DecisionStatus, set[DecisionStatus]] = {
        DecisionStatus.PROPOSED: {DecisionStatus.ACTIVE, DecisionStatus.REVOKED},
        DecisionStatus.ACTIVE: {DecisionStatus.EXPIRED, DecisionStatus.REVOKED},
        DecisionStatus.SUPERSEDED: set(),
        DecisionStatus.EXPIRED: set(),
        DecisionStatus.REVOKED: set(),
    }
    if target not in allowed[current]:
        raise DecisionLifecycleRejected(
            "invalid_status_transition",
            f"Decision status cannot change from {current.value} to {target.value}",
        )
    if target == DecisionStatus.EXPIRED:
        if item.expires_at is None or as_utc(item.expires_at) > datetime.now(UTC):
            raise DecisionLifecycleRejected(
                "decision_not_due_to_expire",
                "Only a decision whose expires_at has passed can be marked expired",
            )

    item.status = target
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action=f"decision.{target.value}",
        resource_type="decision",
        resource_id=item.id,
        details={"previous_status": current.value, "note": payload.note},
    )
    return item
