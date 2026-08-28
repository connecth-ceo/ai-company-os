import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActionIntent, ActionIntentStatus, Approval, ApprovalStatus
from app.schemas import ActionIntentCreate
from app.services.audit import add_audit_event


class ActionIntentRejected(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def canonical_payload(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def payload_digest(payload: dict) -> str:
    return hashlib.sha256(canonical_payload(payload)).hexdigest()


def verify_payload_integrity(intent: ActionIntent) -> None:
    if payload_digest(intent.payload) != intent.payload_hash:
        raise ActionIntentRejected(
            "payload_integrity_failed",
            "Action intent payload no longer matches its immutable hash",
        )


async def create_action_intent(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor: str,
    payload: ActionIntentCreate,
    now: datetime | None = None,
) -> ActionIntent:
    now = now or datetime.now(UTC)
    digest = payload_digest(payload.payload)
    if payload.idempotency_key:
        existing = await session.scalar(
            select(ActionIntent).where(
                ActionIntent.tenant_id == tenant_id,
                ActionIntent.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            same_request = (
                existing.payload_hash == digest
                and existing.action_type == payload.action_type
                and existing.summary == payload.summary
                and existing.reason == payload.reason
                and existing.risk == payload.risk
                and existing.task_id == payload.task_id
            )
            if not same_request:
                raise ActionIntentRejected(
                    "idempotency_conflict",
                    "Idempotency key is already bound to a different action intent",
                )
            return existing

    approval = Approval(
        tenant_id=tenant_id,
        task_id=payload.task_id,
        action=payload.summary,
        reason=payload.reason,
        risk=payload.risk,
    )
    session.add(approval)
    await session.flush()
    intent = ActionIntent(
        tenant_id=tenant_id,
        task_id=payload.task_id,
        approval_id=approval.id,
        idempotency_key=payload.idempotency_key,
        action_type=payload.action_type,
        summary=payload.summary,
        reason=payload.reason,
        risk=payload.risk,
        payload=payload.payload,
        payload_hash=digest,
        execution_scope="single_use",
        status=ActionIntentStatus.PROPOSED,
        expires_at=now + timedelta(minutes=payload.expires_in_minutes),
    )
    session.add(intent)
    await session.flush()
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="action_intent.proposed",
        resource_type="action_intent",
        resource_id=intent.id,
        details={
            "approval_id": approval.id,
            "action_type": intent.action_type,
            "payload_hash": intent.payload_hash,
            "risk": intent.risk,
            "execution_scope": intent.execution_scope,
            "expires_at": intent.expires_at.isoformat(),
        },
    )
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="approval.requested",
        resource_type="approval",
        resource_id=approval.id,
        details={"task_id": intent.task_id, "risk": intent.risk, "action_intent_id": intent.id},
    )
    return intent


async def decide_linked_action_intent(
    session: AsyncSession,
    *,
    approval: Approval,
    tenant_id: str,
    approved: bool,
    actor: str,
    now: datetime | None = None,
) -> ActionIntent | None:
    intent = await session.scalar(
        select(ActionIntent)
        .where(
            ActionIntent.approval_id == approval.id,
            ActionIntent.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if intent is None:
        return None
    if intent.status != ActionIntentStatus.PROPOSED:
        raise ActionIntentRejected(
            "intent_already_decided",
            "Action intent has already been decided",
        )
    verify_payload_integrity(intent)
    now = now or datetime.now(UTC)
    expires_at = intent.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if now >= expires_at:
        intent.status = ActionIntentStatus.EXPIRED
        intent.decided_at = now
        approval.status = ApprovalStatus.REJECTED
        approval.decided_by = "system"
        approval.decision_note = "Action intent expired before approval"
        approval.decided_at = now
        add_audit_event(
            session,
            tenant_id=tenant_id,
            actor="system",
            action="action_intent.expired",
            resource_type="action_intent",
            resource_id=intent.id,
            details={"approval_id": approval.id, "payload_hash": intent.payload_hash},
        )
        add_audit_event(
            session,
            tenant_id=tenant_id,
            actor="system",
            action="approval.rejected",
            resource_type="approval",
            resource_id=approval.id,
            details={"action_intent_id": intent.id, "reason": "expired"},
        )
        raise ActionIntentRejected(
            "intent_expired",
            "Action intent expired before approval",
        )

    intent.status = ActionIntentStatus.APPROVED if approved else ActionIntentStatus.REJECTED
    intent.decided_at = now
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action=f"action_intent.{intent.status.value}",
        resource_type="action_intent",
        resource_id=intent.id,
        details={
            "approval_id": approval.id,
            "payload_hash": intent.payload_hash,
            "execution_scope": intent.execution_scope,
            "executed": False,
        },
    )
    return intent
