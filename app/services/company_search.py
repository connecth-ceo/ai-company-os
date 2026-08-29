import re
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Decision, DecisionStatus, KnowledgeItem, Memory
from app.schemas import (
    CompanyContextResourceType,
    CompanyContextSearchItem,
    CompanyContextSearchResponse,
)

MAX_CANDIDATES_PER_TYPE = 300
EXCERPT_LENGTH = 320


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _terms(query: str) -> tuple[str, ...]:
    normalized = _normalize(query).casefold()
    tokens = re.findall(r"\w+", normalized, flags=re.UNICODE)
    values = tokens or [normalized]
    return tuple(dict.fromkeys(value for value in values if value))


def _score(query: str, terms: tuple[str, ...], title: str, body: str) -> int:
    normalized_query = _normalize(query).casefold()
    normalized_title = _normalize(title).casefold()
    normalized_body = _normalize(body).casefold()
    score = 0
    if normalized_query in normalized_title:
        score += 18
    elif normalized_query in normalized_body:
        score += 10
    for term in terms:
        if term in normalized_title:
            score += 6
        if term in normalized_body:
            score += 2
    if terms and all(term in f"{normalized_title} {normalized_body}" for term in terms):
        score += 5
    return score


def _excerpt(value: str, terms: tuple[str, ...], limit: int = EXCERPT_LENGTH) -> str:
    normalized = _normalize(value)
    if len(normalized) <= limit:
        return normalized
    lowered = normalized.casefold()
    matches = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    focus = min(matches) if matches else 0
    start = max(0, focus - limit // 4)
    end = min(len(normalized), start + limit)
    if end - start < limit:
        start = max(0, end - limit)
    prefix = "…" if start else ""
    suffix = "…" if end < len(normalized) else ""
    return f"{prefix}{normalized[start:end]}{suffix}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _metadata(**values: str | None) -> dict[str, str]:
    return {key: value for key, value in values.items() if value is not None}


async def search_company_context(
    session: AsyncSession,
    *,
    tenant_id: str,
    query: str,
    resource_types: set[CompanyContextResourceType],
    effective_decisions_only: bool,
    limit: int,
) -> CompanyContextSearchResponse:
    normalized_query = _normalize(query)
    terms = _terms(normalized_query)
    candidates: list[CompanyContextSearchItem] = []

    if CompanyContextResourceType.MEMORY in resource_types:
        memories = list(
            await session.scalars(
                select(Memory)
                .where(Memory.tenant_id == tenant_id)
                .order_by(Memory.created_at.desc())
                .limit(MAX_CANDIDATES_PER_TYPE)
            )
        )
        for item in memories:
            title = item.category
            score = _score(normalized_query, terms, title, item.content)
            if score:
                candidates.append(
                    CompanyContextSearchItem(
                        resource_type=CompanyContextResourceType.MEMORY,
                        resource_id=item.id,
                        title=title,
                        excerpt=_excerpt(item.content, terms),
                        score=score,
                        created_at=item.created_at,
                        metadata=_metadata(
                            category=item.category,
                            source_task_id=item.source_task_id,
                        ),
                    )
                )

    if CompanyContextResourceType.DECISION in resource_types:
        decision_conditions = [Decision.tenant_id == tenant_id]
        if effective_decisions_only:
            now = datetime.now(UTC)
            decision_conditions.extend(
                [
                    Decision.status == DecisionStatus.ACTIVE,
                    Decision.effective_at <= now,
                    or_(Decision.expires_at.is_(None), Decision.expires_at > now),
                ]
            )
        decisions = list(
            await session.scalars(
                select(Decision)
                .where(*decision_conditions)
                .order_by(Decision.created_at.desc())
                .limit(MAX_CANDIDATES_PER_TYPE)
            )
        )
        for item in decisions:
            body = f"{item.choice} {item.rationale}"
            score = _score(normalized_query, terms, item.subject, body)
            if score:
                candidates.append(
                    CompanyContextSearchItem(
                        resource_type=CompanyContextResourceType.DECISION,
                        resource_id=item.id,
                        title=item.subject,
                        excerpt=_excerpt(body, terms),
                        score=score,
                        created_at=item.created_at,
                        metadata=_metadata(
                            status=str(item.status),
                            scope=str(item.scope),
                            decided_by=item.decided_by,
                            task_id=item.task_id,
                        ),
                    )
                )

    if CompanyContextResourceType.KNOWLEDGE in resource_types:
        knowledge_items = list(
            await session.scalars(
                select(KnowledgeItem)
                .where(KnowledgeItem.tenant_id == tenant_id)
                .order_by(KnowledgeItem.created_at.desc())
                .limit(MAX_CANDIDATES_PER_TYPE)
            )
        )
        for item in knowledge_items:
            body = f"{item.content} {item.source or ''}"
            score = _score(normalized_query, terms, item.title, body)
            if score:
                candidates.append(
                    CompanyContextSearchItem(
                        resource_type=CompanyContextResourceType.KNOWLEDGE,
                        resource_id=item.id,
                        title=item.title,
                        excerpt=_excerpt(body, terms),
                        score=score,
                        created_at=item.created_at,
                        metadata=_metadata(source=item.source, task_id=item.task_id),
                    )
                )

    candidates.sort(
        key=lambda item: (
            item.score,
            _as_utc(item.created_at),
            item.resource_type.value,
            item.resource_id,
        ),
        reverse=True,
    )
    items = candidates[:limit]
    return CompanyContextSearchResponse(
        query=normalized_query,
        total=len(candidates),
        items=items,
    )
