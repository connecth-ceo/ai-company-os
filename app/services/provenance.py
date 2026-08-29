import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Decision,
    KnowledgeItem,
    ProvenanceRecord,
    ProvenanceSourceType,
    ProvenanceSubjectType,
    ProvenanceVerificationStatus,
    TaskRun,
)

MAX_SOURCE_URIS = 20
URL_PATTERN = re.compile(r"https?://[^\s<>'\"\])}]+", re.IGNORECASE)


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def extract_source_uris(content: str) -> list[str]:
    """Extract bounded, normalized HTTP(S) citations without fetching them."""
    sources: list[str] = []
    seen: set[str] = set()
    for match in URL_PATTERN.findall(content):
        candidate = match.rstrip(".,;:!?")
        try:
            parsed = urlsplit(candidate)
        except ValueError:
            continue
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            continue
        normalized = urlunsplit(
            (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, "")
        )
        if len(normalized) > 2048 or normalized in seen:
            continue
        seen.add(normalized)
        sources.append(normalized)
        if len(sources) >= MAX_SOURCE_URIS:
            break
    return sources


def _idempotency_key(
    *,
    subject_type: ProvenanceSubjectType,
    subject_id: str,
    content_hash: str,
    source_uri: str | None,
    source_record_id: str | None = None,
) -> str:
    canonical = "|".join(
        [
            subject_type.value,
            subject_id,
            content_hash,
            source_uri or "",
            source_record_id or "",
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _add_once(session: AsyncSession, record: ProvenanceRecord) -> ProvenanceRecord:
    existing = await session.scalar(
        select(ProvenanceRecord).where(
            ProvenanceRecord.tenant_id == record.tenant_id,
            ProvenanceRecord.idempotency_key == record.idempotency_key,
        )
    )
    if existing is not None:
        return existing
    session.add(record)
    return record


async def capture_research_provenance(
    session: AsyncSession,
    *,
    tenant_id: str,
    knowledge_item: KnowledgeItem,
    task_run: TaskRun,
    content: str,
    produced_by_agent: str = "Research Agent",
) -> list[ProvenanceRecord]:
    digest = content_sha256(content)
    source_uris = extract_source_uris(content)
    captured: list[ProvenanceRecord] = []
    for source_uri in source_uris or [None]:
        source_type = ProvenanceSourceType.URL if source_uri else ProvenanceSourceType.TASK_RUN
        status = (
            ProvenanceVerificationStatus.OBSERVED
            if source_uri
            else ProvenanceVerificationStatus.UNVERIFIED
        )
        record = ProvenanceRecord(
            tenant_id=tenant_id,
            idempotency_key=_idempotency_key(
                subject_type=ProvenanceSubjectType.KNOWLEDGE,
                subject_id=knowledge_item.id,
                content_hash=digest,
                source_uri=source_uri,
            ),
            subject_type=ProvenanceSubjectType.KNOWLEDGE,
            knowledge_item_id=knowledge_item.id,
            task_id=knowledge_item.task_id,
            task_run_id=task_run.id,
            source_type=source_type,
            source_uri=source_uri,
            source_label=source_uri or "Research Agent output",
            claim_reference="research_brief",
            produced_by_agent=produced_by_agent,
            content_hash=digest,
            verification_status=status,
            record_metadata={
                "artifact": "research",
                "citation_count": len(source_uris),
            },
        )
        captured.append(await _add_once(session, record))
    return captured


async def capture_decision_provenance(
    session: AsyncSession,
    *,
    tenant_id: str,
    decision: Decision,
    actor: str,
) -> list[ProvenanceRecord]:
    digest = content_sha256(decision.rationale)
    inherited: list[ProvenanceRecord] = []
    if decision.task_id:
        inherited = list(
            await session.scalars(
                select(ProvenanceRecord)
                .where(
                    ProvenanceRecord.tenant_id == tenant_id,
                    ProvenanceRecord.task_id == decision.task_id,
                    ProvenanceRecord.subject_type == ProvenanceSubjectType.KNOWLEDGE,
                )
                .order_by(ProvenanceRecord.captured_at.desc())
                .limit(MAX_SOURCE_URIS)
            )
        )

    inputs: list[tuple[str | None, ProvenanceRecord | None]] = []
    seen_uris: set[str | None] = set()
    for source in inherited:
        if source.source_uri in seen_uris:
            continue
        seen_uris.add(source.source_uri)
        inputs.append((source.source_uri, source))
    for source_uri in extract_source_uris(decision.rationale):
        if source_uri in seen_uris:
            continue
        seen_uris.add(source_uri)
        inputs.append((source_uri, None))
    if not inputs:
        inputs.append((None, None))

    captured: list[ProvenanceRecord] = []
    for source_uri, source_record in inputs[:MAX_SOURCE_URIS]:
        if source_record is not None:
            source_type = ProvenanceSourceType.INHERITED
            status = source_record.verification_status
            label = source_record.source_label
        elif source_uri:
            source_type = ProvenanceSourceType.URL
            status = ProvenanceVerificationStatus.OBSERVED
            label = source_uri
        else:
            source_type = ProvenanceSourceType.MANUAL
            status = ProvenanceVerificationStatus.UNVERIFIED
            label = "Decision rationale"
        record = ProvenanceRecord(
            tenant_id=tenant_id,
            idempotency_key=_idempotency_key(
                subject_type=ProvenanceSubjectType.DECISION,
                subject_id=decision.id,
                content_hash=digest,
                source_uri=source_uri,
                source_record_id=source_record.id if source_record else None,
            ),
            subject_type=ProvenanceSubjectType.DECISION,
            decision_id=decision.id,
            task_id=decision.task_id,
            task_run_id=source_record.task_run_id if source_record else None,
            source_record_id=source_record.id if source_record else None,
            source_type=source_type,
            source_uri=source_uri,
            source_label=label,
            claim_reference="decision_rationale",
            produced_by_agent=actor,
            content_hash=digest,
            verification_status=status,
            record_metadata={"inherited": source_record is not None},
        )
        captured.append(await _add_once(session, record))
    return captured
