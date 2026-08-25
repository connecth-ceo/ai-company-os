import hmac
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db import get_session
from app.models import Task, TaskStatus
from app.services.audit import add_audit_event
from app.services.task_service import execute_task_with_new_session

router = APIRouter(prefix="/integrations/telegram", tags=["Telegram"])


def require_telegram_configuration(settings: Settings) -> None:
    if not (
        settings.telegram_bot_token
        and settings.telegram_webhook_secret
        and settings.telegram_allowed_chat_id
    ):
        raise HTTPException(status_code=503, detail="Telegram integration is not configured")


@router.post("/webhook", include_in_schema=False)
async def telegram_webhook(
    update: dict[str, Any],
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_session)],
    secret: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
) -> dict[str, Any]:
    require_telegram_configuration(settings)
    if not hmac.compare_digest(secret or "", settings.telegram_webhook_secret or ""):
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")

    message = update.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    if chat_id != settings.telegram_allowed_chat_id:
        raise HTTPException(status_code=403, detail="Telegram chat is not allowed")
    text = str(message.get("text") or "").strip()
    if not text:
        return {"ok": True}

    if text in {"/start", "/help"}:
        return {
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "업무 내용을 자연어로 보내주세요. /status 로 최근 업무를 확인할 수 있습니다.",
        }

    if text == "/status":
        query = (
            select(Task)
            .where(Task.tenant_id == settings.default_tenant_id)
            .order_by(Task.created_at.desc())
            .limit(5)
        )
        tasks = list(await session.scalars(query))
        summary = "\n".join(f"• {task.title}: {task.status.value}" for task in tasks)
        return {
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": summary or "아직 등록된 업무가 없습니다.",
        }

    idempotency_key = f"telegram:{update.get('update_id', '')}"
    query = select(Task).where(
        Task.tenant_id == settings.default_tenant_id,
        Task.idempotency_key == idempotency_key,
    )
    task = (await session.scalars(query)).first()
    if task is None:
        title = text.replace("\n", " ")[:60]
        task = Task(
            tenant_id=settings.default_tenant_id,
            idempotency_key=idempotency_key,
            title=title,
            request=text,
            source="telegram",
            external_ref=chat_id,
            status=TaskStatus.DISPATCHED,
        )
        session.add(task)
        await session.flush()
        add_audit_event(
            session,
            tenant_id=task.tenant_id,
            actor=f"telegram:{chat_id}",
            action="task.created",
            resource_type="task",
            resource_id=task.id,
            details={"source": "telegram"},
        )
        await session.commit()
        if settings.task_execution_mode == "worker":
            from app.worker import execute_task_job

            execute_task_job.delay(task.id)
        else:
            background_tasks.add_task(execute_task_with_new_session, task.id, True, False)

    return {
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": f"업무를 접수했습니다.\nID: {task.id}\n완료되면 이 채팅으로 보고드리겠습니다.",
    }
