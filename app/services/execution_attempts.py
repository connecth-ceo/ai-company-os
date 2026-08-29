from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.catalog import ConnectorPolicyError, require_connector_action
from app.connectors.contracts import (
    ConnectorPayloadError,
    require_payload_contract,
    validate_connector_payload,
)
from app.core.config import Settings, get_settings
from app.db import SessionLocal
from app.models import (
    ActionIntent,
    ActionIntentStatus,
    Approval,
    ApprovalStatus,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    ExecutionReceipt,
    uuid_str,
)
from app.schemas import (
    ExecutionAttemptClaim,
    ExecutionAttemptComplete,
    ExecutionAttemptPreflightRead,
    ExecutionAttemptPrepare,
    ExecutionAttemptRecoveryRead,
)
from app.services.action_intents import verify_payload_integrity
from app.services.audit import add_audit_event


class ExecutionAttemptRejected(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require_connector(
    connector_key: str,
    action_type: str,
    *,
    phase: Literal["prepare", "claim", "complete"],
) -> None:
    try:
        require_connector_action(connector_key, action_type, phase=phase)
    except ConnectorPolicyError as exc:
        raise ExecutionAttemptRejected(exc.code, exc.detail) from exc


def _require_connector_payload(action_type: str, payload: dict) -> None:
    try:
        validate_connector_payload(action_type, payload)
    except ConnectorPayloadError as exc:
        raise ExecutionAttemptRejected(exc.code, exc.detail) from exc


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _record_receipt(
    session: AsyncSession,
    *,
    attempt: ExecutionAttempt,
    outcome: ExecutionAttemptStatus,
    outcome_code: str,
    completed_by: str,
    observed_at: datetime,
    provider_reference_hash: str | None = None,
    response_hash: str | None = None,
) -> ExecutionReceipt:
    receipt = ExecutionReceipt(
        id=uuid_str(),
        tenant_id=attempt.tenant_id,
        execution_attempt_id=attempt.id,
        connector_key=attempt.connector_key,
        action_type=attempt.action_type,
        payload_hash=attempt.payload_hash,
        outcome=outcome,
        outcome_code=outcome_code,
        provider_reference_hash=provider_reference_hash,
        response_hash=response_hash,
        completed_by=completed_by,
        observed_at=observed_at,
    )
    session.add(receipt)
    return receipt


async def get_execution_receipt(
    session: AsyncSession,
    *,
    tenant_id: str,
    attempt_id: str,
) -> ExecutionReceipt:
    receipt = await session.scalar(
        select(ExecutionReceipt).where(
            ExecutionReceipt.execution_attempt_id == attempt_id,
            ExecutionReceipt.tenant_id == tenant_id,
        )
    )
    if receipt is None:
        raise ExecutionAttemptRejected("receipt_not_found", "Execution receipt not found")
    return receipt


async def preflight_execution_attempt(
    session: AsyncSession,
    *,
    tenant_id: str,
    attempt_id: str,
    now: datetime | None = None,
) -> ExecutionAttemptPreflightRead:
    """Diagnose execution blockers without claiming, mutating, or calling a provider."""

    current = now or datetime.now(UTC)
    attempt = await session.scalar(
        select(ExecutionAttempt).where(
            ExecutionAttempt.id == attempt_id,
            ExecutionAttempt.tenant_id == tenant_id,
        )
    )
    if attempt is None:
        raise ExecutionAttemptRejected("attempt_not_found", "Execution attempt not found")

    blockers: list[str] = []
    descriptor = None
    try:
        descriptor = require_connector_action(
            attempt.connector_key,
            attempt.action_type,
            phase="claim",
        )
    except ConnectorPolicyError as exc:
        blockers.append(exc.code)

    contract = None
    try:
        contract = require_payload_contract(attempt.action_type)
    except ConnectorPayloadError as exc:
        blockers.append(exc.code)

    intent = await session.scalar(
        select(ActionIntent).where(
            ActionIntent.id == attempt.action_intent_id,
            ActionIntent.tenant_id == tenant_id,
        )
    )
    payload_valid = True
    approval_valid = True
    if attempt.status != ExecutionAttemptStatus.PREPARED:
        blockers.append("attempt_not_prepared")
    if intent is None:
        blockers.append("intent_not_found")
        payload_valid = False
        approval_valid = False
    else:
        try:
            verify_payload_integrity(intent)
        except ValueError:
            blockers.append("payload_integrity_failed")
            payload_valid = False
        if intent.payload_hash != attempt.payload_hash:
            blockers.append("payload_hash_mismatch")
            payload_valid = False
        if intent.action_type != attempt.action_type:
            blockers.append("action_type_mismatch")
            payload_valid = False
        try:
            validate_connector_payload(intent.action_type, intent.payload)
        except ConnectorPayloadError as exc:
            blockers.append(exc.code)
            payload_valid = False
        if intent.status != ActionIntentStatus.APPROVED:
            blockers.append("intent_not_approved")
            approval_valid = False
        if current >= _as_utc(intent.expires_at):
            blockers.append("intent_expired")
            approval_valid = False

        approval = await session.scalar(
            select(Approval).where(
                Approval.id == attempt.approval_id,
                Approval.tenant_id == tenant_id,
            )
        )
        if (
            approval is None
            or approval.id != intent.approval_id
            or approval.status != ApprovalStatus.APPROVED
        ):
            blockers.append("approval_not_approved")
            approval_valid = False

    external_execution_available = bool(
        descriptor is not None and descriptor.external_execution_available
    )
    if not external_execution_available:
        blockers.append("external_adapter_unavailable")

    unique_blockers = list(dict.fromkeys(blockers))
    return ExecutionAttemptPreflightRead(
        generated_at=current,
        attempt_id=attempt.id,
        connector_key=attempt.connector_key,
        action_type=attempt.action_type,
        schema_id=contract.schema_id if contract else None,
        schema_version=contract.version if contract else None,
        status=attempt.status,
        payload_hash=attempt.payload_hash,
        payload_valid=payload_valid,
        approval_valid=approval_valid,
        external_execution_available=external_execution_available,
        executable=not unique_blockers,
        blockers=unique_blockers,
    )


async def _load_intent(
    session: AsyncSession,
    *,
    tenant_id: str,
    intent_id: str,
) -> ActionIntent:
    intent = await session.scalar(
        select(ActionIntent)
        .where(
            ActionIntent.id == intent_id,
            ActionIntent.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if intent is None:
        raise ExecutionAttemptRejected("intent_not_found", "Action intent not found")
    return intent


async def _verify_execution_ready(
    session: AsyncSession,
    *,
    intent: ActionIntent,
    tenant_id: str,
    expected_payload_hash: str,
    current: datetime,
) -> Approval:
    try:
        verify_payload_integrity(intent)
    except ValueError as exc:
        raise ExecutionAttemptRejected("payload_integrity_failed", str(exc)) from exc
    if intent.payload_hash != expected_payload_hash:
        raise ExecutionAttemptRejected(
            "payload_hash_mismatch",
            "Expected payload hash does not match the approved action intent",
        )
    if intent.status == ActionIntentStatus.CONSUMED:
        raise ExecutionAttemptRejected(
            "intent_already_consumed",
            "Single-use action intent has already been consumed",
        )
    if intent.status != ActionIntentStatus.APPROVED:
        raise ExecutionAttemptRejected(
            "intent_not_approved",
            "Action intent must be approved before execution preparation",
        )
    if current >= _as_utc(intent.expires_at):
        intent.status = ActionIntentStatus.EXPIRED
        add_audit_event(
            session,
            tenant_id=tenant_id,
            actor="system:execution-gateway",
            action="action_intent.expired",
            resource_type="action_intent",
            resource_id=intent.id,
            details={
                "approval_id": intent.approval_id,
                "payload_hash": intent.payload_hash,
                "phase": "execution_preparation",
            },
        )
        raise ExecutionAttemptRejected(
            "intent_expired",
            "Action intent expired before execution preparation",
        )

    approval = await session.scalar(
        select(Approval)
        .where(
            Approval.id == intent.approval_id,
            Approval.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if approval is None or approval.status != ApprovalStatus.APPROVED:
        raise ExecutionAttemptRejected(
            "approval_not_approved",
            "Linked approval must be approved before execution preparation",
        )
    return approval


async def prepare_execution_attempt(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor: str,
    intent_id: str,
    payload: ExecutionAttemptPrepare,
    now: datetime | None = None,
) -> ExecutionAttempt:
    current = now or datetime.now(UTC)
    intent = await _load_intent(session, tenant_id=tenant_id, intent_id=intent_id)
    approval = await _verify_execution_ready(
        session,
        intent=intent,
        tenant_id=tenant_id,
        expected_payload_hash=payload.expected_payload_hash,
        current=current,
    )
    _require_connector(payload.connector_key, intent.action_type, phase="prepare")
    _require_connector_payload(intent.action_type, intent.payload)

    existing_key = await session.scalar(
        select(ExecutionAttempt).where(
            ExecutionAttempt.tenant_id == tenant_id,
            ExecutionAttempt.idempotency_key == payload.idempotency_key,
        )
    )
    if existing_key is not None:
        if (
            existing_key.action_intent_id != intent.id
            or existing_key.connector_key != payload.connector_key
            or existing_key.payload_hash != payload.expected_payload_hash
            or existing_key.timeout_seconds != payload.timeout_seconds
        ):
            raise ExecutionAttemptRejected(
                "idempotency_conflict",
                "Idempotency key is already bound to a different execution attempt",
            )
        return existing_key

    existing_intent = await session.scalar(
        select(ExecutionAttempt).where(ExecutionAttempt.action_intent_id == intent.id)
    )
    if existing_intent is not None:
        raise ExecutionAttemptRejected(
            "single_use_attempt_exists",
            "Single-use action intent already has an execution attempt",
        )

    attempt = ExecutionAttempt(
        tenant_id=tenant_id,
        action_intent_id=intent.id,
        approval_id=approval.id,
        idempotency_key=payload.idempotency_key,
        connector_key=payload.connector_key,
        action_type=intent.action_type,
        payload_hash=intent.payload_hash,
        status=ExecutionAttemptStatus.PREPARED,
        timeout_seconds=payload.timeout_seconds,
        requested_by=actor,
    )
    session.add(attempt)
    await session.flush()
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="execution_attempt.prepared",
        resource_type="execution_attempt",
        resource_id=attempt.id,
        details={
            "action_intent_id": intent.id,
            "approval_id": approval.id,
            "connector_key": attempt.connector_key,
            "action_type": attempt.action_type,
            "payload_hash": attempt.payload_hash,
            "timeout_seconds": attempt.timeout_seconds,
            "external_call_started": False,
        },
    )
    return attempt


async def claim_execution_attempt(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor: str,
    attempt_id: str,
    payload: ExecutionAttemptClaim,
    now: datetime | None = None,
) -> ExecutionAttempt:
    current = now or datetime.now(UTC)
    attempt = await session.scalar(
        select(ExecutionAttempt)
        .where(
            ExecutionAttempt.id == attempt_id,
            ExecutionAttempt.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if attempt is None:
        raise ExecutionAttemptRejected("attempt_not_found", "Execution attempt not found")
    if attempt.payload_hash != payload.expected_payload_hash:
        raise ExecutionAttemptRejected(
            "payload_hash_mismatch",
            "Expected payload hash does not match the prepared execution attempt",
        )
    if attempt.status == ExecutionAttemptStatus.CLAIMED:
        if attempt.claimed_by == payload.claimed_by:
            return attempt
        raise ExecutionAttemptRejected(
            "attempt_already_claimed",
            "Execution attempt was already claimed by another executor",
        )
    if attempt.status != ExecutionAttemptStatus.PREPARED:
        raise ExecutionAttemptRejected(
            "attempt_not_prepared",
            "Only a prepared execution attempt can be claimed",
        )
    _require_connector(attempt.connector_key, attempt.action_type, phase="claim")

    intent = await _load_intent(
        session,
        tenant_id=tenant_id,
        intent_id=attempt.action_intent_id,
    )
    try:
        await _verify_execution_ready(
            session,
            intent=intent,
            tenant_id=tenant_id,
            expected_payload_hash=payload.expected_payload_hash,
            current=current,
        )
        _require_connector_payload(intent.action_type, intent.payload)
    except ExecutionAttemptRejected as exc:
        if exc.code == "intent_expired":
            attempt.status = ExecutionAttemptStatus.FAILED
            attempt.completed_at = current
            attempt.outcome_code = "intent_expired_before_claim"
            receipt = _record_receipt(
                session,
                attempt=attempt,
                outcome=ExecutionAttemptStatus.FAILED,
                outcome_code=attempt.outcome_code,
                completed_by=actor,
                observed_at=current,
            )
            add_audit_event(
                session,
                tenant_id=tenant_id,
                actor=actor,
                action="execution_attempt.failed",
                resource_type="execution_attempt",
                resource_id=attempt.id,
                details={
                    "receipt_id": receipt.id,
                    "action_intent_id": intent.id,
                    "connector_key": attempt.connector_key,
                    "payload_hash": attempt.payload_hash,
                    "outcome_code": attempt.outcome_code,
                    "external_call_started": False,
                },
            )
        raise

    attempt.status = ExecutionAttemptStatus.CLAIMED
    attempt.claimed_by = payload.claimed_by
    attempt.claimed_at = current
    attempt.deadline_at = min(
        _as_utc(intent.expires_at),
        current + timedelta(seconds=attempt.timeout_seconds),
    )
    intent.status = ActionIntentStatus.CONSUMED
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="execution_attempt.claimed",
        resource_type="execution_attempt",
        resource_id=attempt.id,
        details={
            "action_intent_id": intent.id,
            "connector_key": attempt.connector_key,
            "payload_hash": attempt.payload_hash,
            "claimed_by": attempt.claimed_by,
            "deadline_at": attempt.deadline_at.isoformat(),
            "external_call_started": False,
        },
    )
    return attempt


async def complete_execution_attempt(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor: str,
    attempt_id: str,
    payload: ExecutionAttemptComplete,
    now: datetime | None = None,
) -> ExecutionAttempt:
    current = now or datetime.now(UTC)
    attempt = await session.scalar(
        select(ExecutionAttempt)
        .where(
            ExecutionAttempt.id == attempt_id,
            ExecutionAttempt.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if attempt is None:
        raise ExecutionAttemptRejected("attempt_not_found", "Execution attempt not found")
    if attempt.payload_hash != payload.expected_payload_hash:
        raise ExecutionAttemptRejected(
            "payload_hash_mismatch",
            "Expected payload hash does not match the claimed execution attempt",
        )

    terminal_statuses = {
        ExecutionAttemptStatus.SUCCEEDED,
        ExecutionAttemptStatus.FAILED,
        ExecutionAttemptStatus.UNCERTAIN,
    }
    outcome = ExecutionAttemptStatus(payload.outcome)
    if attempt.status in terminal_statuses:
        if attempt.status == outcome and attempt.outcome_code == payload.outcome_code:
            receipt = await session.scalar(
                select(ExecutionReceipt).where(
                    ExecutionReceipt.execution_attempt_id == attempt.id
                )
            )
            if receipt is None:
                _record_receipt(
                    session,
                    attempt=attempt,
                    outcome=outcome,
                    outcome_code=payload.outcome_code,
                    completed_by=payload.completed_by,
                    observed_at=attempt.completed_at or current,
                    provider_reference_hash=payload.provider_reference_hash,
                    response_hash=payload.response_hash,
                )
                return attempt
            if (
                receipt.provider_reference_hash == payload.provider_reference_hash
                and receipt.response_hash == payload.response_hash
            ):
                return attempt
            raise ExecutionAttemptRejected(
                "completion_receipt_conflict",
                "Execution receipt is already bound to different provider proof hashes",
            )
        raise ExecutionAttemptRejected(
            "attempt_already_completed",
            "Execution attempt already has a different terminal outcome",
        )
    if attempt.status != ExecutionAttemptStatus.CLAIMED:
        raise ExecutionAttemptRejected(
            "attempt_not_claimed",
            "Execution attempt must be claimed before recording an outcome",
        )
    _require_connector(attempt.connector_key, attempt.action_type, phase="complete")

    intent = await _load_intent(
        session,
        tenant_id=tenant_id,
        intent_id=attempt.action_intent_id,
    )
    try:
        verify_payload_integrity(intent)
    except ValueError as exc:
        raise ExecutionAttemptRejected("payload_integrity_failed", str(exc)) from exc
    if intent.payload_hash != payload.expected_payload_hash:
        raise ExecutionAttemptRejected(
            "payload_hash_mismatch",
            "Approved payload hash changed before outcome recording",
        )
    if intent.status != ActionIntentStatus.CONSUMED:
        raise ExecutionAttemptRejected(
            "intent_not_consumed",
            "Action intent must remain consumed while recording an execution outcome",
        )
    _require_connector_payload(intent.action_type, intent.payload)

    attempt.status = outcome
    attempt.outcome_code = payload.outcome_code
    attempt.completed_at = current
    receipt = _record_receipt(
        session,
        attempt=attempt,
        outcome=outcome,
        outcome_code=payload.outcome_code,
        completed_by=payload.completed_by,
        observed_at=current,
        provider_reference_hash=payload.provider_reference_hash,
        response_hash=payload.response_hash,
    )
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action=f"execution_attempt.{outcome.value}",
        resource_type="execution_attempt",
        resource_id=attempt.id,
        details={
            "receipt_id": receipt.id,
            "action_intent_id": intent.id,
            "connector_key": attempt.connector_key,
            "payload_hash": attempt.payload_hash,
            "completed_by": payload.completed_by,
            "outcome_code": attempt.outcome_code,
            "provider_proof_present": payload.provider_reference_hash is not None,
            "external_call_performed_by_this_service": False,
        },
    )
    return attempt


async def run_execution_attempt_recovery(
    session: AsyncSession,
    *,
    tenant_id: str,
    settings: Settings,
    dry_run: bool = True,
    limit: int | None = None,
    now: datetime | None = None,
    actor: str = "system:execution-attempt-recovery",
) -> ExecutionAttemptRecoveryRead:
    if not dry_run and not settings.execution_attempt_recovery_enabled:
        raise ExecutionAttemptRejected(
            "execution_attempt_recovery_disabled",
            "Execution attempt recovery is disabled; use dry-run or enable it explicitly",
        )

    current = now or datetime.now(UTC)
    run_limit = limit or settings.execution_attempt_recovery_limit
    stale_attempts = list(
        await session.scalars(
            select(ExecutionAttempt)
            .where(
                ExecutionAttempt.tenant_id == tenant_id,
                ExecutionAttempt.status == ExecutionAttemptStatus.CLAIMED,
                ExecutionAttempt.deadline_at <= current,
            )
            .order_by(ExecutionAttempt.deadline_at, ExecutionAttempt.id)
            .limit(run_limit)
            .with_for_update()
        )
    )
    attempt_ids = [attempt.id for attempt in stale_attempts]
    if dry_run:
        return ExecutionAttemptRecoveryRead(
            generated_at=current,
            enabled=settings.execution_attempt_recovery_enabled,
            dry_run=True,
            scanned=len(stale_attempts),
            stale=len(stale_attempts),
            transitioned=0,
            attempt_ids=attempt_ids,
        )

    for attempt in stale_attempts:
        attempt.status = ExecutionAttemptStatus.UNCERTAIN
        attempt.completed_at = current
        attempt.outcome_code = "deadline_exceeded_without_confirmation"
        receipt = _record_receipt(
            session,
            attempt=attempt,
            outcome=ExecutionAttemptStatus.UNCERTAIN,
            outcome_code=attempt.outcome_code,
            completed_by=actor,
            observed_at=current,
        )
        add_audit_event(
            session,
            tenant_id=tenant_id,
            actor=actor,
            action="execution_attempt.uncertain",
            resource_type="execution_attempt",
            resource_id=attempt.id,
            details={
                "receipt_id": receipt.id,
                "action_intent_id": attempt.action_intent_id,
                "connector_key": attempt.connector_key,
                "payload_hash": attempt.payload_hash,
                "outcome_code": attempt.outcome_code,
                "automatic_retry_started": False,
            },
        )
    return ExecutionAttemptRecoveryRead(
        generated_at=current,
        enabled=True,
        dry_run=False,
        scanned=len(stale_attempts),
        stale=len(stale_attempts),
        transitioned=len(stale_attempts),
        attempt_ids=attempt_ids,
    )


async def dispatch_scheduled_execution_attempt_recovery(
    *,
    settings: Settings | None = None,
) -> ExecutionAttemptRecoveryRead:
    runtime_settings = settings or get_settings()
    if not runtime_settings.execution_attempt_recovery_enabled:
        return ExecutionAttemptRecoveryRead(
            generated_at=datetime.now(UTC),
            enabled=False,
            dry_run=False,
            scanned=0,
            stale=0,
            transitioned=0,
            attempt_ids=[],
        )

    async with SessionLocal() as session:
        result = await run_execution_attempt_recovery(
            session,
            tenant_id=runtime_settings.default_tenant_id,
            settings=runtime_settings,
            dry_run=False,
        )
        await session.commit()
        return result
