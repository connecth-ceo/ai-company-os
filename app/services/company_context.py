from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Decision, KnowledgeItem, Memory


def compact(value: str, limit: int = 1200) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}…"


async def build_company_context(
    session: AsyncSession,
    tenant_id: str,
    *,
    per_section: int = 8,
    max_chars: int = 12_000,
) -> str:
    memory_query = (
        select(Memory)
        .where(Memory.tenant_id == tenant_id)
        .order_by(Memory.created_at.desc())
        .limit(per_section)
    )
    decision_query = (
        select(Decision)
        .where(Decision.tenant_id == tenant_id)
        .order_by(Decision.created_at.desc())
        .limit(per_section)
    )
    knowledge_query = (
        select(KnowledgeItem)
        .where(KnowledgeItem.tenant_id == tenant_id)
        .order_by(KnowledgeItem.created_at.desc())
        .limit(per_section)
    )

    memories = list(await session.scalars(memory_query))
    decisions = list(await session.scalars(decision_query))
    knowledge_items = list(await session.scalars(knowledge_query))

    sections: list[str] = []
    if memories:
        lines = [f"- [{item.category}] {compact(item.content)}" for item in memories]
        sections.append("COMPANY MEMORIES:\n" + "\n".join(lines))
    if decisions:
        lines = [
            f"- {compact(item.subject, 240)}: {compact(item.choice)} "
            f"(rationale: {compact(item.rationale)})"
            for item in decisions
        ]
        sections.append("CEO DECISIONS:\n" + "\n".join(lines))
    if knowledge_items:
        lines = [
            f"- {compact(item.title, 240)}: {compact(item.content)}" for item in knowledge_items
        ]
        sections.append("COMPANY KNOWLEDGE:\n" + "\n".join(lines))

    context = "\n\n".join(sections)
    if len(context) <= max_chars:
        return context
    return f"{context[: max_chars - 1]}…"
