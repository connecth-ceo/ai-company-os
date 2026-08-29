import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.models import (
    AttentionFollowUp,
    AttentionLevel,
    CommitmentSourceType,
    Project,
    Task,
)
from app.schemas import (
    AttentionAcknowledgementCreate,
    AttentionFollowUpCreate,
    AttentionFollowUpRead,
    CommitmentCreate,
)
from app.services import commitments, portfolio
from app.services.attention import attention_follow_up_status, build_attention_queue
from app.services.attention_acknowledgements import (
    AttentionAcknowledgementRejected,
    acknowledge_attention,
)
from app.services.audit import add_audit_event

DEFAULT_DUE_HOURS = {
    AttentionLevel.CRITICAL: 4,
    AttentionLevel.DECISION: 12,
    AttentionLevel.ACTION: 24,
    AttentionLevel.WATCH: 72,
    AttentionLevel.INFO: 168,
}
TASK_PRIORITY = {
    AttentionLevel.CRITICAL: 5,
    AttentionLevel.DECISION: 4,
    AttentionLevel.ACTION: 3,
    AttentionLevel.WATCH: 2,
    AttentionLevel.INFO: 1,
}


class AttentionFollowUpRejected(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _request_hash(payload: AttentionFollowUpCreate) -> str:
    values = payload.model_dump(mode="json", exclude={"idempotency_key"})
    encoded = json.dumps(
        values,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _task_idempotency_key(request_hash: str) -> str:
    return f"attention-follow-up-task:{request_hash}"


def _acknowledgement_idempotency_key(request_hash: str) -> str:
    return f"attention-follow-up-ack:{request_hash}"


def as_attention_follow_up_read(item: AttentionFollowUp) -> AttentionFollowUpRead:
    return AttentionFollowUpRead(
        id=item.id,
        tenant_id=item.tenant_id,
        attention_id=item.attention_id,
        fingerprint=item.fingerprint,
        task_id=item.task_id,
        commitment_id=item.commitment_id,
        task_status=item.task.status,
        commitment_status=item.commitment.status,
        status=attention_follow_up_status(item),
        created_by=item.created_by,
        note=item.note,
        created_at=item.created_at,
    )


async def list_attention_follow_ups(
    session: AsyncSession,
    *,
    tenant_id: str,
    attention_id: str | None = None,
    limit: int = 100,
) -> list[AttentionFollowUpRead]:
    conditions = [AttentionFollowUp.tenant_id == tenant_id]
    if attention_id is not None:
        conditions.append(AttentionFollowUp.attention_id == attention_id)
    query = (
        select(AttentionFollowUp)
        .where(*conditions)
        .options(
            selectinload(AttentionFollowUp.task),
            selectinload(AttentionFollowUp.commitment),
        )
        .order_by(AttentionFollowUp.created_at.desc())
        .limit(limit)
    )
    return [as_attention_follow_up_read(item) for item in await session.scalars(query)]


async def create_attention_follow_up(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor: str,
    attention_id: str,
    payload: AttentionFollowUpCreate,
    settings: Settings,
    now: datetime | None = None,
) -> AttentionFollowUpRead:
    request_hash = _request_hash(payload)
    existing = await session.scalar(
        select(AttentionFollowUp)
        .where(
            AttentionFollowUp.tenant_id == tenant_id,
            AttentionFollowUp.idempotency_key == payload.idempotency_key,
        )
        .options(
            selectinload(AttentionFollowUp.task),
            selectinload(AttentionFollowUp.commitment),
        )
    )
    if existing is not None:
        if (
            existing.attention_id != attention_id
            or existing.fingerprint != payload.expected_fingerprint
            or existing.request_hash != request_hash
        ):
            raise AttentionFollowUpRejected(
                "idempotency_conflict",
                "Idempotency key is already bound to a different attention follow-up",
            )
        return as_attention_follow_up_read(existing)

    queue = await build_attention_queue(
        session,
        tenant_id,
        settings=settings,
        include_acknowledged=True,
        limit=None,
    )
    current = next((item for item in queue.items if item.id == attention_id), None)
    if current is None:
        raise AttentionFollowUpRejected(
            "attention_not_found",
            "Current attention signal not found",
        )
    if current.fingerprint != payload.expected_fingerprint:
        raise AttentionFollowUpRejected(
            "attention_fingerprint_mismatch",
            "Attention signal changed before follow-up creation; refresh and review it again",
        )

    existing_signal = await session.scalar(
        select(AttentionFollowUp)
        .where(
            AttentionFollowUp.tenant_id == tenant_id,
            AttentionFollowUp.attention_id == current.id,
            AttentionFollowUp.fingerprint == current.fingerprint,
        )
        .options(
            selectinload(AttentionFollowUp.task),
            selectinload(AttentionFollowUp.commitment),
        )
    )
    if existing_signal is not None:
        if existing_signal.request_hash != request_hash:
            raise AttentionFollowUpRejected(
                "follow_up_already_exists",
                "This attention signal already has a different follow-up plan",
            )
        return as_attention_follow_up_read(existing_signal)

    try:
        await acknowledge_attention(
            session,
            tenant_id=tenant_id,
            actor=actor,
            attention_id=current.id,
            payload=AttentionAcknowledgementCreate(
                expected_fingerprint=current.fingerprint,
                acknowledged_by=actor,
                note="후속조치 생성으로 확인",
                idempotency_key=_acknowledgement_idempotency_key(request_hash),
            ),
            settings=settings,
        )
    except AttentionAcknowledgementRejected as exc:
        raise AttentionFollowUpRejected(exc.code, exc.detail) from exc

    if current.project_id is not None:
        project = await session.scalar(
            select(Project).where(
                Project.id == current.project_id,
                Project.tenant_id == tenant_id,
            )
        )
        if project is None:
            raise AttentionFollowUpRejected("project_not_found", "Related project not found")
        try:
            portfolio.ensure_project_accepts_tasks(project)
        except portfolio.PortfolioLifecycleRejected as exc:
            raise AttentionFollowUpRejected(exc.code, exc.detail) from exc

    task = Task(
        tenant_id=tenant_id,
        idempotency_key=_task_idempotency_key(request_hash),
        title=(payload.task_title or f"주의 대응: {current.title}")[:240],
        request=payload.task_request
        or (
            "다음 대표 주의 신호에 대한 후속조치를 계획하고 실행 상태를 보고하세요.\n"
            f"주의 종류: {current.kind.value}\n"
            f"수준: {current.level.value}\n"
            f"요약: {current.summary}\n"
            f"권고: {current.recommendation}"
        ),
        priority=TASK_PRIORITY[current.level],
        source="attention",
        external_ref=current.id[:120],
        project_id=current.project_id,
    )
    session.add(task)
    await session.flush()
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="task.created",
        resource_type="task",
        resource_id=task.id,
        details={
            "project_id": task.project_id,
            "parent_task_id": None,
            "attention_id": current.id,
            "execution_started": False,
        },
    )

    due_hours = payload.due_in_hours or DEFAULT_DUE_HOURS[current.level]
    try:
        commitment = await commitments.create_commitment(
            session,
            tenant_id=tenant_id,
            actor=actor,
            payload=CommitmentCreate(
                statement=payload.statement
                or f"{current.title} 후속조치: {current.recommendation}",
                owner_type=payload.owner_type,
                owner_id=payload.owner_id,
                due_at=(now or datetime.now(UTC)) + timedelta(hours=due_hours),
                source_type=CommitmentSourceType.TASK,
                task_id=task.id,
                project_id=current.project_id,
                decision_id=current.resource_id if current.resource_type == "decision" else None,
                provenance={
                    "channel": "attention_follow_up",
                    "attention_id": current.id,
                    "attention_fingerprint": current.fingerprint,
                },
                reminder_policy={
                    "strategy": "attention_level",
                    "attention_level": current.level.value,
                },
            ),
        )
    except commitments.CommitmentLifecycleRejected as exc:
        raise AttentionFollowUpRejected(exc.code, exc.detail) from exc

    follow_up = AttentionFollowUp(
        tenant_id=tenant_id,
        attention_id=current.id,
        fingerprint=current.fingerprint,
        idempotency_key=payload.idempotency_key,
        request_hash=request_hash,
        task_id=task.id,
        commitment_id=commitment.id,
        created_by=actor,
        note=payload.note,
        task=task,
        commitment=commitment,
    )
    session.add(follow_up)
    await session.flush()
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="attention.follow_up_created",
        resource_type=current.resource_type,
        resource_id=current.resource_id,
        details={
            "follow_up_id": follow_up.id,
            "attention_id": current.id,
            "fingerprint": current.fingerprint,
            "task_id": task.id,
            "commitment_id": commitment.id,
            "execution_started": False,
        },
    )
    return as_attention_follow_up_read(follow_up)
