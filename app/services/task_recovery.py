from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Task, TaskRun, TaskStatus, WorkflowRun
from app.services.audit import add_audit_event


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def recover_stale_tasks(
    session: AsyncSession,
    *,
    settings: Settings,
    limit: int | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    if not settings.task_recovery_enabled:
        return {
            "enabled": False,
            "scanned": 0,
            "stale": 0,
            "reset_for_retry": 0,
            "quarantined": 0,
            "redispatch_task_ids": [],
        }

    current_time = now or datetime.now(UTC)
    candidates = list(
        await session.scalars(
            select(Task)
            .where(Task.status.in_((TaskStatus.DISPATCHED, TaskStatus.RUNNING)))
            .order_by(Task.updated_at.asc())
            .limit(limit or settings.task_recovery_limit)
            .with_for_update(skip_locked=True)
        )
    )
    redispatch_task_ids: list[str] = []
    quarantined = 0

    for task in candidates:
        previous_status = task.status
        if task.status == TaskStatus.DISPATCHED:
            stale_after = _utc(task.updated_at) + timedelta(
                seconds=settings.task_dispatch_stale_seconds
            )
            if current_time <= stale_after:
                continue
            run_count = int(
                (
                    await session.scalar(
                        select(func.count(TaskRun.id)).where(TaskRun.task_id == task.id)
                    )
                )
                or 0
            )
            if run_count == 0:
                task.status = TaskStatus.QUEUED
                task.error = None
                redispatch_task_ids.append(task.id)
                add_audit_event(
                    session,
                    tenant_id=task.tenant_id,
                    actor="system",
                    action="task.recovered_before_start",
                    resource_type="task",
                    resource_id=task.id,
                    details={"previous_status": TaskStatus.DISPATCHED, "automatic_retry": True},
                )
                continue
        elif task.status == TaskStatus.RUNNING:
            stale_after = _utc(task.updated_at) + timedelta(
                seconds=settings.task_timeout_seconds + settings.task_recovery_grace_seconds
            )
            if current_time <= stale_after:
                continue
        else:
            continue

        quarantined += 1
        error = (
            "Stale task execution quarantined; automatic retry is disabled because "
            "provider work may already have started"
        )
        task.status = TaskStatus.FAILED
        task.error = error
        running_runs = list(
            await session.scalars(
                select(TaskRun).where(
                    TaskRun.task_id == task.id,
                    TaskRun.status == TaskStatus.RUNNING,
                )
            )
        )
        for run in running_runs:
            run.status = TaskStatus.FAILED
            run.feedback = error
            run.finished_at = current_time
        if running_runs:
            workflow_runs = list(
                await session.scalars(
                    select(WorkflowRun).where(
                        WorkflowRun.task_run_id.in_([run.id for run in running_runs])
                    )
                )
            )
            for workflow_run in workflow_runs:
                workflow_run.status = "failed"
                workflow_run.error = error
                workflow_run.finished_at = current_time
        add_audit_event(
            session,
            tenant_id=task.tenant_id,
            actor="system",
            action="task.stale_execution_quarantined",
            resource_type="task",
            resource_id=task.id,
            details={
                "previous_status": previous_status,
                "automatic_retry": False,
                "running_runs": len(running_runs),
            },
        )

    await session.commit()
    return {
        "enabled": True,
        "scanned": len(candidates),
        "stale": len(redispatch_task_ids) + quarantined,
        "reset_for_retry": len(redispatch_task_ids),
        "quarantined": quarantined,
        "redispatch_task_ids": redispatch_task_ids,
    }


async def recover_stale_tasks_with_new_session(settings: Settings) -> dict[str, object]:
    from app.db import SessionLocal

    async with SessionLocal() as session:
        return await recover_stale_tasks(session, settings=settings)
