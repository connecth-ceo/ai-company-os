import asyncio

from celery import Celery

from app.core.config import get_settings
from app.services.attention_automation import dispatch_scheduled_attention_auto_plan
from app.services.briefing_delivery import dispatch_scheduled_briefing
from app.services.delegation_execution import (
    DelegationExecutionError,
    execute_delegation_with_new_session,
)
from app.services.task_service import TaskExecutionError, execute_task_with_new_session

settings = get_settings()
celery_app = Celery("ai_company_os", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": settings.task_timeout_seconds + 300},
    result_expires=86400,
    task_soft_time_limit=settings.task_timeout_seconds + 30,
    task_time_limit=settings.task_timeout_seconds + 60,
    timezone=settings.briefing_timezone,
    enable_utc=True,
    beat_schedule={
        "daily-briefing-delivery-tick": {
            "task": "ai_company.dispatch_daily_briefing",
            "schedule": 300.0,
        },
        "attention-auto-plan-tick": {
            "task": "ai_company.dispatch_attention_auto_plan",
            "schedule": float(settings.attention_auto_plan_interval_seconds),
        },
    },
)


@celery_app.task(
    bind=True,
    name="ai_company.execute_task",
    max_retries=max(settings.task_max_attempts - 1, 0),
)
def execute_task_job(self, task_id: str) -> None:
    try:
        delivery_info = self.request.delivery_info or {}
        recover_running = bool(delivery_info.get("redelivered"))
        asyncio.run(execute_task_with_new_session(task_id, False, True, recover_running))
    except TaskExecutionError as exc:
        countdown = min(2 ** (self.request.retries + 1), 30)
        raise self.retry(exc=exc, countdown=countdown) from exc


@celery_app.task(bind=True, name="ai_company.execute_delegation", max_retries=0)
def execute_delegation_job(self, delegation_id: str) -> None:
    del self
    try:
        asyncio.run(execute_delegation_with_new_session(delegation_id, True))
    except DelegationExecutionError:
        raise


@celery_app.task(name="ai_company.dispatch_daily_briefing", max_retries=0)
def dispatch_daily_briefing_job() -> dict[str, str | int | None]:
    result = asyncio.run(dispatch_scheduled_briefing(settings=settings))
    return {
        "outcome": result.outcome.value,
        "delivery_id": result.delivery_id,
        "attempt_count": result.attempt_count,
    }


@celery_app.task(name="ai_company.dispatch_attention_auto_plan", max_retries=0)
def dispatch_attention_auto_plan_job() -> dict[str, str | int | bool]:
    result = asyncio.run(dispatch_scheduled_attention_auto_plan(settings=settings))
    return {
        "rule_version": result.rule_version,
        "enabled": result.enabled,
        "scanned": result.scanned,
        "eligible": result.eligible,
        "created": result.created,
        "skipped": result.skipped,
    }
