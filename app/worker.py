import asyncio

from celery import Celery

from app.core.config import get_settings
from app.services.task_service import TaskExecutionError, execute_task_with_new_session

settings = get_settings()
celery_app = Celery("ai_company_os", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_track_started=True, task_serializer="json", accept_content=["json"])


@celery_app.task(
    bind=True,
    name="ai_company.execute_task",
    max_retries=max(settings.task_max_attempts - 1, 0),
)
def execute_task_job(self, task_id: str) -> None:
    try:
        asyncio.run(execute_task_with_new_session(task_id, False, True))
    except TaskExecutionError as exc:
        countdown = min(2 ** (self.request.retries + 1), 30)
        raise self.retry(exc=exc, countdown=countdown) from exc
