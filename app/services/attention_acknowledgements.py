from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import AttentionAcknowledgement
from app.schemas import AttentionAcknowledgementCreate
from app.services.attention import build_attention_queue
from app.services.audit import add_audit_event


class AttentionAcknowledgementRejected(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


async def list_attention_acknowledgements(
    session: AsyncSession,
    *,
    tenant_id: str,
    attention_id: str | None = None,
    limit: int = 100,
) -> list[AttentionAcknowledgement]:
    conditions = [AttentionAcknowledgement.tenant_id == tenant_id]
    if attention_id is not None:
        conditions.append(AttentionAcknowledgement.attention_id == attention_id)
    query = (
        select(AttentionAcknowledgement)
        .where(*conditions)
        .order_by(AttentionAcknowledgement.created_at.desc())
        .limit(limit)
    )
    return list(await session.scalars(query))


async def acknowledge_attention(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor: str,
    attention_id: str,
    payload: AttentionAcknowledgementCreate,
    settings: Settings,
) -> AttentionAcknowledgement:
    existing = await session.scalar(
        select(AttentionAcknowledgement).where(
            AttentionAcknowledgement.tenant_id == tenant_id,
            AttentionAcknowledgement.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        same_request = (
            existing.attention_id == attention_id
            and existing.fingerprint == payload.expected_fingerprint
            and existing.acknowledged_by == payload.acknowledged_by
            and existing.note == payload.note
        )
        if not same_request:
            raise AttentionAcknowledgementRejected(
                "idempotency_conflict",
                "Idempotency key is already bound to a different acknowledgement",
            )
        return existing

    queue = await build_attention_queue(
        session,
        tenant_id,
        settings=settings,
        include_acknowledged=True,
        limit=None,
    )
    current = next((item for item in queue.items if item.id == attention_id), None)
    if current is None:
        raise AttentionAcknowledgementRejected(
            "attention_not_found",
            "Current attention signal not found",
        )
    if current.fingerprint != payload.expected_fingerprint:
        raise AttentionAcknowledgementRejected(
            "attention_fingerprint_mismatch",
            "Attention signal changed before acknowledgement; refresh and review it again",
        )

    already_acknowledged = await session.scalar(
        select(AttentionAcknowledgement).where(
            AttentionAcknowledgement.tenant_id == tenant_id,
            AttentionAcknowledgement.attention_id == attention_id,
            AttentionAcknowledgement.fingerprint == current.fingerprint,
        )
    )
    if already_acknowledged is not None:
        return already_acknowledged

    acknowledgement = AttentionAcknowledgement(
        tenant_id=tenant_id,
        attention_id=current.id,
        fingerprint=current.fingerprint,
        idempotency_key=payload.idempotency_key,
        level=current.level,
        kind=current.kind,
        resource_type=current.resource_type,
        resource_id=current.resource_id,
        acknowledged_by=payload.acknowledged_by,
        note=payload.note,
    )
    session.add(acknowledgement)
    await session.flush()
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=payload.acknowledged_by or actor,
        action="attention.acknowledged",
        resource_type=current.resource_type,
        resource_id=current.resource_id,
        details={
            "acknowledgement_id": acknowledgement.id,
            "attention_id": current.id,
            "fingerprint": current.fingerprint,
            "level": current.level.value,
            "kind": current.kind.value,
        },
    )
    return acknowledgement
