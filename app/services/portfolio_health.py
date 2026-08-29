from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Goal, GoalStatus, Project, ProjectStatus, Task, TaskStatus
from app.schemas import (
    PortfolioGoalHealthRead,
    PortfolioHealthLevel,
    PortfolioHealthRead,
    PortfolioHealthSummaryRead,
    PortfolioProjectHealthRead,
)

RULE_VERSION = "portfolio-health-v1"
DUE_SOON_DAYS = 14
OPEN_GOAL_STATUSES = {GoalStatus.PLANNED, GoalStatus.ACTIVE, GoalStatus.ON_HOLD}
OPEN_PROJECT_STATUSES = {
    ProjectStatus.PLANNED,
    ProjectStatus.ACTIVE,
    ProjectStatus.ON_HOLD,
}
ACTIVE_TASK_STATUSES = {
    TaskStatus.QUEUED,
    TaskStatus.DISPATCHED,
    TaskStatus.RUNNING,
}


def _completion_percent(completed: int, total: int) -> int:
    return round(completed * 100 / total) if total else 0


def _project_health(
    project: Project,
    *,
    total_tasks: int,
    failed_tasks: int,
) -> tuple[PortfolioHealthLevel, str]:
    status = ProjectStatus(project.status)
    if status in {ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED}:
        return PortfolioHealthLevel.CLOSED, "project_closed"
    if status == ProjectStatus.ON_HOLD:
        return PortfolioHealthLevel.ACTION, "project_on_hold"
    if failed_tasks:
        return PortfolioHealthLevel.ACTION, "failed_tasks"
    if status == ProjectStatus.PLANNED:
        return PortfolioHealthLevel.WATCH, "project_not_started"
    if total_tasks == 0:
        return PortfolioHealthLevel.WATCH, "active_without_tasks"
    return PortfolioHealthLevel.HEALTHY, "on_track"


def _goal_health(
    goal: Goal,
    *,
    current_date: date,
    total_projects: int,
    failed_tasks: int,
) -> tuple[PortfolioHealthLevel, str]:
    status = GoalStatus(goal.status)
    if status in {GoalStatus.ACHIEVED, GoalStatus.CANCELLED, GoalStatus.ARCHIVED}:
        return PortfolioHealthLevel.CLOSED, "goal_closed"
    if goal.target_date and goal.target_date < current_date:
        return PortfolioHealthLevel.CRITICAL, "target_date_overdue"
    if status == GoalStatus.ON_HOLD:
        return PortfolioHealthLevel.ACTION, "goal_on_hold"
    if failed_tasks:
        return PortfolioHealthLevel.ACTION, "failed_tasks"
    if goal.target_date and goal.target_date <= current_date + timedelta(days=DUE_SOON_DAYS):
        return PortfolioHealthLevel.WATCH, "target_date_due_soon"
    if status == GoalStatus.PLANNED:
        return PortfolioHealthLevel.WATCH, "goal_not_started"
    if total_projects == 0:
        return PortfolioHealthLevel.WATCH, "active_without_projects"
    return PortfolioHealthLevel.HEALTHY, "on_track"


async def build_portfolio_health(
    session: AsyncSession,
    tenant_id: str,
    *,
    now: datetime | None = None,
    item_limit: int = 100,
) -> PortfolioHealthRead:
    """Compute tenant-safe portfolio health without an AI call or side effect."""

    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    else:
        current = current.astimezone(UTC)
    current_date = current.date()

    goals = list(
        await session.scalars(
            select(Goal).where(Goal.tenant_id == tenant_id).order_by(Goal.created_at.desc())
        )
    )
    projects = list(
        await session.scalars(
            select(Project)
            .where(Project.tenant_id == tenant_id)
            .order_by(Project.created_at.desc())
        )
    )

    task_rows = (
        await session.execute(
            select(
                Task.project_id,
                func.count(Task.id).label("total_tasks"),
                func.sum(case((Task.status.in_(ACTIVE_TASK_STATUSES), 1), else_=0)).label(
                    "active_tasks"
                ),
                func.sum(case((Task.status == TaskStatus.COMPLETED, 1), else_=0)).label(
                    "completed_tasks"
                ),
                func.sum(case((Task.status == TaskStatus.FAILED, 1), else_=0)).label(
                    "failed_tasks"
                ),
            )
            .where(
                Task.tenant_id == tenant_id,
                Task.project_id.is_not(None),
            )
            .group_by(Task.project_id)
        )
    ).all()
    task_counts = {
        project_id: {
            "total": int(total or 0),
            "active": int(active or 0),
            "completed": int(completed or 0),
            "failed": int(failed or 0),
        }
        for project_id, total, active, completed, failed in task_rows
    }

    project_items: list[PortfolioProjectHealthRead] = []
    project_counts_by_goal: dict[str, dict[str, int]] = {}
    for project in projects:
        counts = task_counts.get(
            project.id,
            {"total": 0, "active": 0, "completed": 0, "failed": 0},
        )
        health_level, health_reason = _project_health(
            project,
            total_tasks=counts["total"],
            failed_tasks=counts["failed"],
        )
        project_items.append(
            PortfolioProjectHealthRead(
                id=project.id,
                title=project.title,
                goal_id=project.goal_id,
                status=ProjectStatus(project.status),
                health_level=health_level,
                health_reason=health_reason,
                total_tasks=counts["total"],
                active_tasks=counts["active"],
                completed_tasks=counts["completed"],
                failed_tasks=counts["failed"],
                completion_percent=_completion_percent(counts["completed"], counts["total"]),
            )
        )
        if project.goal_id:
            goal_counts = project_counts_by_goal.setdefault(
                project.goal_id,
                {"projects": 0, "open_projects": 0, "tasks": 0, "completed": 0, "failed": 0},
            )
            goal_counts["projects"] += 1
            if ProjectStatus(project.status) in OPEN_PROJECT_STATUSES:
                goal_counts["open_projects"] += 1
            goal_counts["tasks"] += counts["total"]
            goal_counts["completed"] += counts["completed"]
            goal_counts["failed"] += counts["failed"]

    goal_items: list[PortfolioGoalHealthRead] = []
    for goal in goals:
        counts = project_counts_by_goal.get(
            goal.id,
            {"projects": 0, "open_projects": 0, "tasks": 0, "completed": 0, "failed": 0},
        )
        health_level, health_reason = _goal_health(
            goal,
            current_date=current_date,
            total_projects=counts["projects"],
            failed_tasks=counts["failed"],
        )
        goal_items.append(
            PortfolioGoalHealthRead(
                id=goal.id,
                title=goal.title,
                status=GoalStatus(goal.status),
                target_date=goal.target_date,
                days_to_target=(goal.target_date - current_date).days if goal.target_date else None,
                health_level=health_level,
                health_reason=health_reason,
                total_projects=counts["projects"],
                open_projects=counts["open_projects"],
                total_tasks=counts["tasks"],
                completed_tasks=counts["completed"],
                failed_tasks=counts["failed"],
                completion_percent=_completion_percent(counts["completed"], counts["tasks"]),
            )
        )

    all_health_levels = [item.health_level for item in [*goal_items, *project_items]]
    health_counts = {
        level.value: sum(1 for current_level in all_health_levels if current_level == level)
        for level in PortfolioHealthLevel
    }
    total_tasks = sum(item.total_tasks for item in project_items)
    completed_tasks = sum(item.completed_tasks for item in project_items)
    summary = PortfolioHealthSummaryRead(
        open_goals=sum(1 for goal in goals if GoalStatus(goal.status) in OPEN_GOAL_STATUSES),
        overdue_goals=sum(1 for item in goal_items if item.health_reason == "target_date_overdue"),
        due_soon_goals=sum(
            1 for item in goal_items if item.health_reason == "target_date_due_soon"
        ),
        open_projects=sum(
            1 for project in projects if ProjectStatus(project.status) in OPEN_PROJECT_STATUSES
        ),
        on_hold_projects=sum(
            1 for project in projects if ProjectStatus(project.status) == ProjectStatus.ON_HOLD
        ),
        projects_with_failed_tasks=sum(1 for item in project_items if item.failed_tasks > 0),
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        completion_percent=_completion_percent(completed_tasks, total_tasks),
        health_counts=health_counts,
    )
    return PortfolioHealthRead(
        rule_version=RULE_VERSION,
        generated_at=current,
        summary=summary,
        goals=goal_items[:item_limit],
        projects=project_items[:item_limit],
    )

