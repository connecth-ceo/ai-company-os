import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import (
    AuditEvent,
    Task,
    TaskRun,
    TaskStatus,
    WorkflowDefinition,
    WorkflowRun,
)
from app.services.task_recovery import recover_stale_tasks
from app.services.task_service import (
    execute_task_with_new_session,
    mark_task_worker_failure_with_new_session,
)
from app.worker import celery_app


def test_celery_delivery_timeout_exceeds_task_hard_limit():
    visibility_timeout = celery_app.conf.broker_transport_options["visibility_timeout"]

    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert visibility_timeout > celery_app.conf.task_time_limit


def test_daily_briefing_tick_is_registered_without_ai_work():
    schedule = celery_app.conf.beat_schedule["daily-briefing-delivery-tick"]

    assert schedule["task"] == "ai_company.dispatch_daily_briefing"
    assert schedule["schedule"] == 300.0
    assert "ai_company.dispatch_daily_briefing" in celery_app.tasks


def test_attention_auto_plan_tick_is_registered_fail_closed():
    schedule = celery_app.conf.beat_schedule["attention-auto-plan-tick"]

    assert schedule["task"] == "ai_company.dispatch_attention_auto_plan"
    assert schedule["schedule"] == 300.0
    assert "ai_company.dispatch_attention_auto_plan" in celery_app.tasks


def test_execution_attempt_recovery_tick_is_registered_fail_closed():
    schedule = celery_app.conf.beat_schedule["execution-attempt-recovery-tick"]

    assert schedule["task"] == "ai_company.dispatch_execution_attempt_recovery"
    assert schedule["schedule"] == 60.0
    assert "ai_company.dispatch_execution_attempt_recovery" in celery_app.tasks


def test_stale_task_recovery_tick_is_registered():
    schedule = celery_app.conf.beat_schedule["task-recovery-tick"]

    assert schedule["task"] == "ai_company.dispatch_task_recovery"
    assert schedule["schedule"] == 60.0
    assert "ai_company.dispatch_task_recovery" in celery_app.tasks


async def test_redelivered_worker_task_recovers_interrupted_run():
    async with SessionLocal() as session:
        task = Task(
            title="Worker recovery",
            request="재전달된 업무를 복구해줘.",
            status=TaskStatus.RUNNING,
        )
        session.add(task)
        await session.flush()
        session.add(TaskRun(task_id=task.id, status=TaskStatus.RUNNING, attempt=1))
        await session.commit()
        task_id = task.id

    await execute_task_with_new_session(task_id, False, True, True)

    async with SessionLocal() as session:
        recovered_task = await session.get(Task, task_id)
        runs = list(
            await session.scalars(
                select(TaskRun).where(TaskRun.task_id == task_id).order_by(TaskRun.attempt)
            )
        )

    assert recovered_task is not None
    assert recovered_task.status == TaskStatus.COMPLETED
    assert [run.status for run in runs] == [TaskStatus.FAILED, TaskStatus.COMPLETED]
    assert runs[0].feedback == "Recovered after background worker redelivery"


async def test_concurrent_delivery_creates_only_one_task_run():
    async with SessionLocal() as session:
        task = Task(
            title="Concurrent claim",
            request="동시에 전달되어도 한 번만 실행해줘.",
            status=TaskStatus.DISPATCHED,
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    await asyncio.gather(
        execute_task_with_new_session(task_id, False, True),
        execute_task_with_new_session(task_id, False, True),
    )

    async with SessionLocal() as session:
        runs = list(await session.scalars(select(TaskRun).where(TaskRun.task_id == task_id)))
        completed_task = await session.get(Task, task_id)

    assert completed_task is not None
    assert completed_task.status == TaskStatus.COMPLETED
    assert len(runs) == 1


async def test_redelivery_after_completion_is_a_noop():
    async with SessionLocal() as session:
        task = Task(
            title="Already complete",
            request="완료된 업무",
            status=TaskStatus.COMPLETED,
            result="done",
        )
        session.add(task)
        await session.flush()
        session.add(TaskRun(task_id=task.id, status=TaskStatus.COMPLETED, attempt=1))
        await session.commit()
        task_id = task.id

    await execute_task_with_new_session(task_id, False, True, True)

    async with SessionLocal() as session:
        runs = list(await session.scalars(select(TaskRun).where(TaskRun.task_id == task_id)))

    assert len(runs) == 1


async def test_unexpected_worker_failure_is_visible_on_the_task_and_audit_log():
    async with SessionLocal() as session:
        task = Task(
            title="Unexpected worker failure",
            request="Worker 경계 오류를 기록해줘.",
            status=TaskStatus.RUNNING,
        )
        session.add(task)
        await session.flush()
        run = TaskRun(task_id=task.id, status=TaskStatus.RUNNING, attempt=1)
        session.add(run)
        await session.flush()
        definition = WorkflowDefinition(
            workflow_key="general_v1",
            version="1.0.0",
            name="General",
            description="Test workflow",
            definition={},
            checksum="0" * 64,
        )
        session.add(definition)
        await session.flush()
        workflow_run = WorkflowRun(
            tenant_id=task.tenant_id,
            task_id=task.id,
            task_run_id=run.id,
            definition_id=definition.id,
            workflow_key="general_v1",
            workflow_version="1.0.0",
            status="running",
            definition_snapshot={},
            execution_plan={},
        )
        session.add(workflow_run)
        await session.commit()
        task_id = task.id
        run_id = run.id
        workflow_run_id = workflow_run.id

    await mark_task_worker_failure_with_new_session(
        task_id,
        RuntimeError("future attached to a different loop"),
    )

    async with SessionLocal() as session:
        failed_task = await session.get(Task, task_id)
        failed_run = await session.get(TaskRun, run_id)
        failed_workflow = await session.get(WorkflowRun, workflow_run_id)
        audit = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.resource_id == task_id,
                AuditEvent.action == "task.worker_failed",
            )
        )

    assert failed_task is not None
    assert failed_task.status == TaskStatus.FAILED
    assert failed_task.error == "RuntimeError: future attached to a different loop"
    assert failed_run is not None
    assert failed_run.status == TaskStatus.FAILED
    assert failed_workflow is not None
    assert failed_workflow.status == "failed"
    assert audit is not None


async def test_stale_dispatch_without_a_run_is_reset_for_safe_redispatch():
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        task = Task(
            title="Stale dispatch before start",
            request="실행 전 정체 업무를 복구해줘.",
            status=TaskStatus.DISPATCHED,
            updated_at=now - timedelta(minutes=10),
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    settings = get_settings().model_copy(
        update={"task_recovery_enabled": True, "task_dispatch_stale_seconds": 300}
    )
    async with SessionLocal() as session:
        result = await recover_stale_tasks(session, settings=settings, now=now)

    async with SessionLocal() as session:
        recovered_task = await session.get(Task, task_id)
        audit = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.resource_id == task_id,
                AuditEvent.action == "task.recovered_before_start",
            )
        )

    assert result["reset_for_retry"] == 1
    assert result["redispatch_task_ids"] == [task_id]
    assert recovered_task is not None
    assert recovered_task.status == TaskStatus.QUEUED
    assert audit is not None
