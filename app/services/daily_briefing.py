from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models import (
    Approval,
    ApprovalStatus,
    Commitment,
    CommitmentStatus,
    Task,
    TaskStatus,
)
from app.services.attention import build_attention_queue

MAX_BRIEFING_CHARS = 3_800


def limit_briefing_text(text: str) -> str:
    if len(text) <= MAX_BRIEFING_CHARS:
        return text
    suffix = "\n… 전체 내용은 CEO Desk에서 확인해 주세요."
    shortened = text[: MAX_BRIEFING_CHARS - len(suffix)].rsplit("\n", 1)[0]
    return f"{shortened}{suffix}"


async def build_daily_briefing(
    session: AsyncSession,
    tenant_id: str,
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> str:
    """Build a read-only briefing from company state without an AI call."""

    current = now or datetime.now(UTC)
    runtime_settings = settings or get_settings()
    since = current - timedelta(hours=24)
    task_counts = dict(
        (
            await session.execute(
                select(Task.status, func.count(Task.id))
                .where(Task.tenant_id == tenant_id, Task.created_at >= since)
                .group_by(Task.status)
            )
        ).all()
    )
    pending_approvals = int(
        (
            await session.scalar(
                select(func.count(Approval.id)).where(
                    Approval.tenant_id == tenant_id,
                    Approval.status == ApprovalStatus.PENDING,
                )
            )
        )
        or 0
    )
    recent_tasks = list(
        await session.scalars(
            select(Task)
            .where(Task.tenant_id == tenant_id)
            .order_by(Task.created_at.desc())
            .limit(5)
        )
    )
    pending_commitment_conditions = [
        Commitment.tenant_id == tenant_id,
        Commitment.status.in_([CommitmentStatus.OPEN, CommitmentStatus.IN_PROGRESS]),
    ]
    overdue_commitments = int(
        (
            await session.scalar(
                select(func.count(Commitment.id)).where(
                    *pending_commitment_conditions,
                    Commitment.due_at < current,
                )
            )
        )
        or 0
    )
    due_soon_commitments = int(
        (
            await session.scalar(
                select(func.count(Commitment.id)).where(
                    *pending_commitment_conditions,
                    Commitment.due_at >= current,
                    Commitment.due_at <= current + timedelta(hours=24),
                )
            )
        )
        or 0
    )
    attention_queue = await build_attention_queue(
        session,
        tenant_id,
        settings=runtime_settings,
        now=current,
        limit=5,
    )

    completed = task_counts.get(TaskStatus.COMPLETED, 0)
    failed = task_counts.get(TaskStatus.FAILED, 0)
    active = sum(
        task_counts.get(status, 0)
        for status in (TaskStatus.QUEUED, TaskStatus.DISPATCHED, TaskStatus.RUNNING)
    )
    lines = [
        "☀️ AI Company OS 데일리 브리핑 "
        f"({current.astimezone(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M')} KST)",
        "",
        "최근 24시간",
        f"• 완료 {completed}건 · 진행/대기 {active}건 · 실패 {failed}건",
        f"• 승인 대기 {pending_approvals}건",
        f"• 약속 지연 {overdue_commitments}건 · 24시간 내 마감 {due_soon_commitments}건",
        "• 대표 확인 필요 "
        f"{attention_queue.counts['decision'] + attention_queue.counts['critical']}건",
        "",
        "최근 업무",
    ]
    if recent_tasks:
        lines.extend(f"• [{task.status.value}] {task.title}" for task in recent_tasks)
    else:
        lines.append("• 아직 등록된 업무가 없습니다.")
    if attention_queue.items:
        level_labels = {
            "info": "정보",
            "watch": "관찰",
            "action": "행동",
            "decision": "결정",
            "critical": "긴급",
        }
        lines.extend(("", "대표 주의 큐"))
        for item in attention_queue.items:
            lines.append(f"• [{level_labels[item.level.value]}] {item.title}: {item.summary}")
            lines.append(f"  ↳ {item.recommendation}")
    return limit_briefing_text("\n".join(lines))
