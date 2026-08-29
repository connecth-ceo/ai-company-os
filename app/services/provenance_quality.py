from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ProvenanceRecord,
    ProvenanceReview,
    ProvenanceSubjectType,
    ProvenanceVerificationStatus,
)
from app.schemas import (
    ProvenanceQualityItemRead,
    ProvenanceQualityLevel,
    ProvenanceQualityRead,
    ProvenanceQualitySummaryRead,
)

RULE_VERSION = "provenance-quality-v1"
LEVEL_ORDER = {
    ProvenanceQualityLevel.HEALTHY: 0,
    ProvenanceQualityLevel.WATCH: 1,
    ProvenanceQualityLevel.ACTION: 2,
    ProvenanceQualityLevel.CRITICAL: 3,
}
REASON_ORDER = {
    "rejected": 0,
    "unverified_decision": 1,
    "unverified_knowledge": 2,
    "observed_decision": 3,
    "observed_knowledge": 4,
    "verified": 5,
}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _classify(
    status: ProvenanceVerificationStatus,
    subject_type: ProvenanceSubjectType,
) -> tuple[ProvenanceQualityLevel, str]:
    if status == ProvenanceVerificationStatus.REJECTED:
        return ProvenanceQualityLevel.CRITICAL, "rejected"
    if status == ProvenanceVerificationStatus.UNVERIFIED:
        if subject_type == ProvenanceSubjectType.DECISION:
            return ProvenanceQualityLevel.CRITICAL, "unverified_decision"
        return ProvenanceQualityLevel.ACTION, "unverified_knowledge"
    if status == ProvenanceVerificationStatus.OBSERVED:
        if subject_type == ProvenanceSubjectType.DECISION:
            return ProvenanceQualityLevel.ACTION, "observed_decision"
        return ProvenanceQualityLevel.WATCH, "observed_knowledge"
    return ProvenanceQualityLevel.HEALTHY, "verified"


async def build_provenance_quality(
    session: AsyncSession,
    tenant_id: str,
    *,
    include_verified: bool = False,
    limit: int = 100,
    now: datetime | None = None,
) -> ProvenanceQualityRead:
    """Build a tenant-safe, read-only provenance quality queue without an AI call."""

    current = _as_utc(now or datetime.now(UTC))
    records = list(
        await session.scalars(
            select(ProvenanceRecord).where(ProvenanceRecord.tenant_id == tenant_id)
        )
    )
    review_rows = (
        await session.execute(
            select(
                ProvenanceReview.provenance_record_id,
                func.count(ProvenanceReview.id),
                func.max(ProvenanceReview.created_at),
            )
            .where(ProvenanceReview.tenant_id == tenant_id)
            .group_by(ProvenanceReview.provenance_record_id)
        )
    ).all()
    review_details = {
        record_id: (int(review_count or 0), _as_utc(latest_reviewed_at))
        for record_id, review_count, latest_reviewed_at in review_rows
        if latest_reviewed_at is not None
    }

    items: list[ProvenanceQualityItemRead] = []
    for record in records:
        status = ProvenanceVerificationStatus(record.verification_status)
        subject_type = ProvenanceSubjectType(record.subject_type)
        quality_level, quality_reason = _classify(status, subject_type)
        review_count, latest_reviewed_at = review_details.get(record.id, (0, None))
        items.append(
            ProvenanceQualityItemRead(
                id=record.id,
                subject_type=subject_type,
                source_type=record.source_type,
                source_label=record.source_label,
                source_uri=record.source_uri,
                knowledge_item_id=record.knowledge_item_id,
                decision_id=record.decision_id,
                task_id=record.task_id,
                verification_status=status,
                quality_level=quality_level,
                quality_reason=quality_reason,
                content_hash=record.content_hash,
                captured_at=_as_utc(record.captured_at),
                review_count=review_count,
                latest_reviewed_at=latest_reviewed_at,
            )
        )

    counts = {
        level.value: sum(1 for item in items if item.quality_level == level)
        for level in ProvenanceQualityLevel
    }
    verified_records = sum(
        1 for item in items if item.verification_status == ProvenanceVerificationStatus.VERIFIED
    )
    rejected_records = sum(
        1 for item in items if item.verification_status == ProvenanceVerificationStatus.REJECTED
    )
    needs_review_records = sum(
        1
        for item in items
        if item.verification_status
        in {
            ProvenanceVerificationStatus.UNVERIFIED,
            ProvenanceVerificationStatus.OBSERVED,
        }
    )
    summary = ProvenanceQualitySummaryRead(
        total_records=len(items),
        verified_records=verified_records,
        rejected_records=rejected_records,
        needs_review_records=needs_review_records,
        verification_coverage_percent=(round(verified_records * 100 / len(items)) if items else 0),
        quality_counts=counts,
    )

    selected = [
        item
        for item in items
        if include_verified or item.quality_level != ProvenanceQualityLevel.HEALTHY
    ]
    selected.sort(
        key=lambda item: (
            -LEVEL_ORDER[item.quality_level],
            REASON_ORDER[item.quality_reason],
            0 if item.subject_type == ProvenanceSubjectType.DECISION else 1,
            item.captured_at,
            item.id,
        )
    )
    return ProvenanceQualityRead(
        rule_version=RULE_VERSION,
        generated_at=current,
        summary=summary,
        items=selected[:limit],
    )
