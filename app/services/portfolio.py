from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Goal, GoalStatus, Project, ProjectStatus, Task, TaskStatus
from app.schemas import GoalTransition, ProjectTransition
from app.services.audit import add_audit_event


class PortfolioLifecycleRejected(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


GOAL_TRANSITIONS: dict[GoalStatus, set[GoalStatus]] = {
    GoalStatus.PLANNED: {GoalStatus.ACTIVE, GoalStatus.CANCELLED},
    GoalStatus.ACTIVE: {GoalStatus.ON_HOLD, GoalStatus.ACHIEVED, GoalStatus.CANCELLED},
    GoalStatus.ON_HOLD: {GoalStatus.ACTIVE, GoalStatus.CANCELLED},
    GoalStatus.ACHIEVED: {GoalStatus.ARCHIVED},
    GoalStatus.CANCELLED: {GoalStatus.ARCHIVED},
    GoalStatus.ARCHIVED: set(),
}

PROJECT_TRANSITIONS: dict[ProjectStatus, set[ProjectStatus]] = {
    ProjectStatus.PLANNED: {ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED},
    ProjectStatus.ACTIVE: {
        ProjectStatus.ON_HOLD,
        ProjectStatus.COMPLETED,
    },
    ProjectStatus.ON_HOLD: {ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED},
    ProjectStatus.COMPLETED: {ProjectStatus.ARCHIVED},
    ProjectStatus.ARCHIVED: set(),
}


def ensure_goal_accepts_projects(item: Goal) -> None:
    if GoalStatus(item.status) in {
        GoalStatus.ACHIEVED,
        GoalStatus.CANCELLED,
        GoalStatus.ARCHIVED,
    }:
        raise PortfolioLifecycleRejected(
            "goal_not_open_for_projects",
            "New projects cannot be linked to a terminal goal",
        )


def ensure_project_accepts_tasks(item: Project) -> None:
    if ProjectStatus(item.status) in {ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED}:
        raise PortfolioLifecycleRejected(
            "project_not_open_for_tasks",
            "New tasks cannot be linked to a completed or archived project",
        )


async def transition_goal(
    session: AsyncSession,
    *,
    item: Goal,
    tenant_id: str,
    actor: str,
    payload: GoalTransition,
) -> Goal:
    current = GoalStatus(item.status)
    target = payload.status
    if target not in GOAL_TRANSITIONS[current]:
        raise PortfolioLifecycleRejected(
            "invalid_goal_status_transition",
            f"Goal status cannot change from {current.value} to {target.value}",
        )

    if target in {GoalStatus.ACHIEVED, GoalStatus.CANCELLED}:
        open_projects = await session.scalar(
            select(func.count(Project.id)).where(
                Project.tenant_id == tenant_id,
                Project.goal_id == item.id,
                Project.status.in_(
                    [ProjectStatus.PLANNED, ProjectStatus.ACTIVE, ProjectStatus.ON_HOLD]
                ),
            )
        )
        if open_projects:
            raise PortfolioLifecycleRejected(
                "goal_has_open_projects",
                "A goal with planned, active, or on-hold projects cannot become terminal",
            )

    item.status = target
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action=f"goal.{target.value}",
        resource_type="goal",
        resource_id=item.id,
        details={"previous_status": current.value, "note": payload.note},
    )
    return item


async def transition_project(
    session: AsyncSession,
    *,
    item: Project,
    tenant_id: str,
    actor: str,
    payload: ProjectTransition,
) -> Project:
    current = ProjectStatus(item.status)
    target = payload.status
    if target not in PROJECT_TRANSITIONS[current]:
        raise PortfolioLifecycleRejected(
            "invalid_project_status_transition",
            f"Project status cannot change from {current.value} to {target.value}",
        )

    if target in {ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED}:
        unfinished = await session.scalar(
            select(func.count(Task.id)).where(
                Task.tenant_id == tenant_id,
                Task.project_id == item.id,
                Task.status.in_(
                    [
                        TaskStatus.QUEUED,
                        TaskStatus.DISPATCHED,
                        TaskStatus.RUNNING,
                    ]
                ),
            )
        )
        if unfinished:
            raise PortfolioLifecycleRejected(
                "project_has_unfinished_tasks",
                "A project with queued, dispatched, or running tasks "
                "cannot be completed or archived",
            )

    item.status = target
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action=f"project.{target.value}",
        resource_type="project",
        resource_id=item.id,
        details={"previous_status": current.value, "note": payload.note},
    )
    return item
