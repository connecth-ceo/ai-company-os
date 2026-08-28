from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Delegation, Task, TaskRun, TaskStatus
from app.services.ai_costs import (
    finalize_delegation_cost,
    release_delegation_cost_reservation,
)
from app.services.audit import add_audit_event


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def recover_stale_delegations(
    session: AsyncSession,
    *,
    settings: Settings,
    tenant_id: str,
    actor: str,
    dry_run: bool = True,
    limit: int = 100,
    now: datetime | None = None,
) -> dict[str, object]:
    current_time = now or datetime.now(UTC)
    candidates = list(
        await session.scalars(
            select(Delegation)
            .where(
                Delegation.tenant_id == tenant_id,
                Delegation.status.in_(("dispatched", "running")),
            )
            .order_by(Delegation.updated_at.asc())
            .limit(limit)
        )
    )
    items: list[dict[str, str]] = []
    reset_count = 0
    quarantined_count = 0

    for candidate in candidates:
        delegation = candidate
        if not dry_run:
            locked = await session.scalar(
                select(Delegation)
                .where(
                    Delegation.id == candidate.id,
                    Delegation.tenant_id == tenant_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if locked is None:
                continue
            delegation = locked
        previous_status = delegation.status
        child = await session.get(Task, delegation.child_task_id)

        if previous_status == "dispatched":
            stale_after = _utc(delegation.updated_at) + timedelta(
                seconds=settings.delegation_dispatch_stale_seconds
            )
            if current_time <= stale_after:
                continue
            retryable = delegation.task_run_id is None and child is not None
            action = "reset_for_retry" if retryable else "quarantine_for_manual_review"
        elif previous_status == "running":
            if delegation.started_at is None:
                stale_after = _utc(delegation.updated_at) + timedelta(
                    seconds=settings.delegation_recovery_grace_seconds
                )
            else:
                stale_after = _utc(delegation.started_at) + timedelta(
                    seconds=(
                        delegation.timeout_seconds + settings.delegation_recovery_grace_seconds
                    )
                )
            if current_time <= stale_after:
                continue
            action = "quarantine_for_manual_review"
        else:
            continue

        items.append(
            {
                "delegation_id": delegation.id,
                "child_task_id": delegation.child_task_id,
                "previous_status": previous_status,
                "action": action,
            }
        )
        if action == "reset_for_retry":
            reset_count += 1
        else:
            quarantined_count += 1
        if dry_run:
            continue

        if action == "reset_for_retry":
            await release_delegation_cost_reservation(session, delegation, settings)
            delegation.status = "created"
            delegation.error = "Recovered stale dispatch before runtime start"
            if child is not None:
                child.status = TaskStatus.QUEUED
                child.error = None
            audit_action = "delegation.recovered_before_start"
        else:
            message = (
                "Stale delegated execution quarantined; manual review is required and "
                "automatic retry is disabled to prevent duplicate provider cost"
            )
            delegation.status = "failed"
            delegation.error = message
            delegation.finished_at = current_time
            if delegation.started_at is not None:
                delegation.duration_ms = max(
                    0,
                    round((current_time - _utc(delegation.started_at)).total_seconds() * 1000),
                )
            if child is not None and child.status in {
                TaskStatus.DISPATCHED,
                TaskStatus.RUNNING,
            }:
                child.status = TaskStatus.FAILED
                child.error = message
            if delegation.task_run_id:
                task_run = await session.get(TaskRun, delegation.task_run_id)
                if task_run is not None and task_run.status == TaskStatus.RUNNING:
                    task_run.status = TaskStatus.FAILED
                    task_run.feedback = message
                    task_run.finished_at = current_time
                    task_run.duration_ms = delegation.duration_ms
                    await finalize_delegation_cost(
                        session,
                        delegation,
                        task_run,
                        settings,
                        usage=None,
                        execution_succeeded=False,
                        now=current_time,
                    )
            audit_action = "delegation.stale_execution_quarantined"
        add_audit_event(
            session,
            tenant_id=tenant_id,
            actor=actor,
            action=audit_action,
            resource_type="delegation",
            resource_id=delegation.id,
            details={
                "child_task_id": delegation.child_task_id,
                "previous_status": previous_status,
                "automatic_retry": False,
            },
        )

    if not dry_run:
        await session.commit()
    return {
        "dry_run": dry_run,
        "scanned": len(candidates),
        "stale": len(items),
        "reset_for_retry": reset_count,
        "quarantined": quarantined_count,
        "items": items,
    }
