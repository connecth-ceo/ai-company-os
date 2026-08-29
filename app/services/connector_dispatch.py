from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.connectors.runtime import (
    ConnectorAdapterRegistry,
    ConnectorInvocation,
    ConnectorRuntimeError,
    build_connector_invocation,
)
from app.db import SessionLocal
from app.models import (
    ActionIntent,
    ActionIntentStatus,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    ExecutionReceipt,
)
from app.schemas import ExecutionAttemptComplete
from app.services.action_intents import verify_payload_integrity
from app.services.execution_attempts import ExecutionAttemptRejected, complete_execution_attempt


async def _load_dispatch_invocation(
    session: AsyncSession,
    *,
    tenant_id: str,
    attempt_id: str,
    expected_payload_hash: str,
    now: datetime,
) -> tuple[ExecutionAttempt, ConnectorInvocation | None]:
    attempt = await session.scalar(
        select(ExecutionAttempt).where(
            ExecutionAttempt.id == attempt_id,
            ExecutionAttempt.tenant_id == tenant_id,
        )
    )
    if attempt is None:
        raise ExecutionAttemptRejected("attempt_not_found", "Execution attempt not found")
    if attempt.payload_hash != expected_payload_hash:
        raise ExecutionAttemptRejected(
            "payload_hash_mismatch",
            "Expected payload hash does not match the claimed execution attempt",
        )
    terminal_statuses = {
        ExecutionAttemptStatus.SUCCEEDED,
        ExecutionAttemptStatus.FAILED,
        ExecutionAttemptStatus.UNCERTAIN,
    }
    if attempt.status in terminal_statuses:
        receipt = await session.scalar(
            select(ExecutionReceipt).where(
                ExecutionReceipt.execution_attempt_id == attempt.id,
                ExecutionReceipt.tenant_id == tenant_id,
            )
        )
        if receipt is None:
            raise ExecutionAttemptRejected(
                "receipt_not_found",
                "Terminal execution attempt has no immutable receipt",
            )
        return attempt, None
    if attempt.status != ExecutionAttemptStatus.CLAIMED:
        raise ExecutionAttemptRejected(
            "attempt_not_claimed",
            "Execution attempt must be claimed before connector dispatch",
        )
    deadline = attempt.deadline_at
    if deadline is not None and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    if deadline is None or now >= deadline:
        raise ExecutionAttemptRejected(
            "attempt_deadline_elapsed",
            "Execution attempt deadline elapsed before connector dispatch",
        )

    intent = await session.scalar(
        select(ActionIntent).where(
            ActionIntent.id == attempt.action_intent_id,
            ActionIntent.tenant_id == tenant_id,
        )
    )
    if intent is None:
        raise ExecutionAttemptRejected("intent_not_found", "Action intent not found")
    try:
        verify_payload_integrity(intent)
    except ValueError as exc:
        raise ExecutionAttemptRejected("payload_integrity_failed", str(exc)) from exc
    if intent.status != ActionIntentStatus.CONSUMED:
        raise ExecutionAttemptRejected(
            "intent_not_consumed",
            "Action intent must remain consumed during connector dispatch",
        )
    if intent.action_type != attempt.action_type:
        raise ExecutionAttemptRejected(
            "action_type_mismatch",
            "Execution attempt action type no longer matches its action intent",
        )
    try:
        invocation = build_connector_invocation(
            attempt_id=attempt.id,
            tenant_id=tenant_id,
            connector_key=attempt.connector_key,
            action_type=attempt.action_type,
            payload=intent.payload,
            expected_payload_hash=expected_payload_hash,
        )
    except ConnectorRuntimeError as exc:
        raise ExecutionAttemptRejected(exc.code, exc.detail) from exc
    return attempt, invocation


async def dispatch_claimed_execution_attempt(
    *,
    tenant_id: str,
    actor: str,
    attempt_id: str,
    expected_payload_hash: str,
    registry: ConnectorAdapterRegistry,
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
    now: datetime | None = None,
) -> ExecutionAttempt:
    """Run a claimed adapter outside DB transactions, then atomically record its receipt."""

    current = now or datetime.now(UTC)
    async with session_factory() as read_session:
        attempt, invocation = await _load_dispatch_invocation(
            read_session,
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            expected_payload_hash=expected_payload_hash,
            now=current,
        )
        if invocation is None:
            read_session.expunge(attempt)
        await read_session.rollback()
    if invocation is None:
        return attempt

    try:
        adapter = registry.require(invocation.connector_key, invocation.action_type)
        result = await registry.execute(invocation)
    except ConnectorRuntimeError as exc:
        raise ExecutionAttemptRejected(exc.code, exc.detail) from exc

    async with session_factory() as write_session:
        completed = await complete_execution_attempt(
            write_session,
            tenant_id=tenant_id,
            actor=actor,
            attempt_id=attempt_id,
            payload=ExecutionAttemptComplete(
                expected_payload_hash=expected_payload_hash,
                outcome=result.outcome.value,
                outcome_code=result.outcome_code,
                completed_by=(f"adapter:{adapter.connector_key}@{adapter.adapter_version}"),
                provider_reference_hash=result.provider_reference_hash,
                response_hash=result.response_hash,
            ),
            now=result.observed_at,
        )
        await write_session.commit()
        return completed
