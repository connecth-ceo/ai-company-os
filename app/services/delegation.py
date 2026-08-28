from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.operational_registry import build_operational_agent_registry
from app.agents.registry import UnknownAgentError
from app.core.config import Settings
from app.models import Approval, ApprovalStatus, Delegation, Task, TaskStatus
from app.schemas import DelegatedTaskCreate


@dataclass(frozen=True, slots=True)
class DelegationRejected(ValueError):
    code: str
    detail: str

    def __str__(self) -> str:
        return self.detail


async def _delegation_depth(session: AsyncSession, parent: Task) -> int:
    current = parent
    visited: set[str] = set()
    depth = 0
    while True:
        if current.id in visited:
            raise DelegationRejected("cycle_detected", "Task hierarchy contains a cycle")
        visited.add(current.id)
        if current.parent_task_id is None:
            return depth + 1
        ancestor = await session.scalar(
            select(Task).where(
                Task.id == current.parent_task_id,
                Task.tenant_id == parent.tenant_id,
            )
        )
        if ancestor is None or ancestor.project_id != parent.project_id:
            raise DelegationRejected(
                "boundary_violation",
                "Task ancestry must stay inside the same tenant and project",
            )
        current = ancestor
        depth += 1


async def create_delegation(
    session: AsyncSession,
    *,
    parent: Task,
    payload: DelegatedTaskCreate,
    settings: Settings,
    initiator: str,
) -> tuple[Delegation, Task]:
    # Serialize concurrent delegation attempts for the same parent on databases
    # that support row locks. SQLite ignores the lock during local tests.
    locked_parent = await session.scalar(
        select(Task)
        .where(Task.id == parent.id, Task.tenant_id == parent.tenant_id)
        .with_for_update()
    )
    if locked_parent is None:
        raise DelegationRejected("parent_missing", "The parent task no longer exists")
    parent = locked_parent

    if parent.status in {TaskStatus.DISPATCHED, TaskStatus.RUNNING}:
        raise DelegationRejected(
            "parent_running", "A running or dispatched task cannot create new delegations"
        )

    pending_approvals = await session.scalar(
        select(func.count(Approval.id)).where(
            Approval.tenant_id == parent.tenant_id,
            Approval.task_id == parent.id,
            Approval.status == ApprovalStatus.PENDING,
        )
    )
    if pending_approvals:
        raise DelegationRejected(
            "approval_pending", "Delegation is paused while the parent task awaits approval"
        )

    child_count = await session.scalar(
        select(func.count(Task.id)).where(
            Task.tenant_id == parent.tenant_id,
            Task.parent_task_id == parent.id,
        )
    )
    if int(child_count or 0) >= settings.delegation_max_children:
        raise DelegationRejected(
            "child_limit", "The parent task reached the maximum number of child tasks"
        )

    depth = await _delegation_depth(session, parent)
    if depth > settings.delegation_max_depth:
        raise DelegationRejected(
            "depth_limit", "The delegation would exceed the maximum delegation depth"
        )

    try:
        definition = build_operational_agent_registry(settings).require(payload.delegated_role)
    except UnknownAgentError as exc:
        raise DelegationRejected(
            "role_not_allowed", "The delegated role is not in the operational agent registry"
        ) from exc

    budget_limits = (
        (payload.token_budget, settings.delegation_max_token_budget, "token_budget"),
        (payload.timeout_seconds, settings.delegation_max_timeout_seconds, "timeout_seconds"),
        (payload.cost_budget_usd, settings.delegation_max_cost_usd, "cost_budget_usd"),
    )
    for requested, maximum, name in budget_limits:
        if requested > maximum:
            raise DelegationRejected(
                "budget_limit", f"{name} exceeds the configured delegation maximum"
            )

    policy_snapshot = {
        "version": "1.0.0",
        "max_depth": settings.delegation_max_depth,
        "max_children": settings.delegation_max_children,
        "depth": depth,
        "delegated_role": definition.key,
        "allowed_tools": list(definition.allowed_tools),
        "permissions": list(definition.permissions),
        "approval_policy": definition.approval_policy,
        "budget": {
            "token_budget": payload.token_budget,
            "timeout_seconds": payload.timeout_seconds,
            "cost_budget_usd": payload.cost_budget_usd,
        },
    }
    child = Task(
        tenant_id=parent.tenant_id,
        title=payload.title,
        request=payload.request,
        priority=payload.priority,
        project_id=parent.project_id,
        parent_task_id=parent.id,
        source="delegation",
    )
    session.add(child)
    await session.flush()
    delegation = Delegation(
        tenant_id=parent.tenant_id,
        project_id=parent.project_id,
        parent_task_id=parent.id,
        child_task_id=child.id,
        initiator=initiator,
        delegated_role=definition.key,
        reason=payload.reason,
        depth=depth,
        token_budget=payload.token_budget,
        timeout_seconds=payload.timeout_seconds,
        cost_budget_usd=payload.cost_budget_usd,
        policy_snapshot=policy_snapshot,
    )
    session.add(delegation)
    await session.flush()
    return delegation, child
