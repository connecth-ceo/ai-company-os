import asyncio

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Task, TaskRun, TaskStatus
from app.services.task_service import execute_task_with_new_session
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
