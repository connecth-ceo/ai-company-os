from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ProvenanceRecord,
    ProvenanceReview,
    ProvenanceVerificationStatus,
)
from app.schemas import ProvenanceReviewCreate
from app.services.audit import add_audit_event


class ProvenanceReviewRejected(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


async def require_provenance_record(
    session: AsyncSession,
    *,
    tenant_id: str,
    record_id: str,
    for_update: bool = False,
) -> ProvenanceRecord:
    query = select(ProvenanceRecord).where(
        ProvenanceRecord.id == record_id,
        ProvenanceRecord.tenant_id == tenant_id,
    )
    if for_update:
        query = query.with_for_update()
    record = await session.scalar(query)
    if record is None:
        raise ProvenanceReviewRejected(
            "provenance_not_found",
            "Provenance record not found",
        )
    return record


async def create_provenance_review(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor: str,
    record_id: str,
    payload: ProvenanceReviewCreate,
) -> ProvenanceReview:
    existing = await session.scalar(
        select(ProvenanceReview).where(
            ProvenanceReview.tenant_id == tenant_id,
            ProvenanceReview.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        same_request = (
            existing.provenance_record_id == record_id
            and existing.decision == payload.decision
            and existing.reviewed_content_hash == payload.expected_content_hash
            and existing.reviewed_by == payload.reviewed_by
            and existing.note == payload.note
        )
        if not same_request:
            raise ProvenanceReviewRejected(
                "idempotency_conflict",
                "Idempotency key is already bound to a different provenance review",
            )
        return existing

    record = await require_provenance_record(
        session,
        tenant_id=tenant_id,
        record_id=record_id,
        for_update=True,
    )
    if record.content_hash != payload.expected_content_hash:
        raise ProvenanceReviewRejected(
            "content_hash_mismatch",
            "Provenance content hash changed before review",
        )

    target_status = ProvenanceVerificationStatus(payload.decision.value)
    if record.verification_status == target_status:
        raise ProvenanceReviewRejected(
            "status_unchanged",
            "Provenance record already has the requested verification status",
        )
    if (
        record.verification_status
        in {
            ProvenanceVerificationStatus.VERIFIED,
            ProvenanceVerificationStatus.REJECTED,
        }
        and not payload.note
    ):
        raise ProvenanceReviewRejected(
            "correction_note_required",
            "Changing a completed provenance review requires a note",
        )

    previous_status = record.verification_status
    previous_status_value = (
        previous_status.value
        if isinstance(previous_status, ProvenanceVerificationStatus)
        else previous_status
    )
    review = ProvenanceReview(
        tenant_id=tenant_id,
        provenance_record_id=record.id,
        idempotency_key=payload.idempotency_key,
        decision=payload.decision,
        previous_status=previous_status,
        reviewed_content_hash=payload.expected_content_hash,
        reviewed_by=payload.reviewed_by,
        note=payload.note,
    )
    session.add(review)
    record.verification_status = target_status
    await session.flush()
    add_audit_event(
        session,
        tenant_id=tenant_id,
        actor=payload.reviewed_by or actor,
        action=f"provenance.{payload.decision.value}",
        resource_type="provenance",
        resource_id=record.id,
        details={
            "review_id": review.id,
            "previous_status": previous_status_value,
            "verification_status": target_status.value,
            "content_hash": record.content_hash,
            "source_record_id": record.source_record_id,
        },
    )
    return review
