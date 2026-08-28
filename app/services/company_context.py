from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Decision, DecisionScope, DecisionStatus, KnowledgeItem, Memory


def compact(value: str, limit: int = 1200) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}…"


async def build_company_context(
    session: AsyncSession,
    tenant_id: str,
    *,
    task_id: str | None = None,
    project_id: str | None = None,
    department: str | None = None,
    per_section: int = 8,
    max_chars: int = 12_000,
) -> str:
    now = datetime.now(UTC)
    scope_conditions = [Decision.scope == DecisionScope.COMPANY]
    if project_id:
        scope_conditions.append(
            and_(
                Decision.scope == DecisionScope.PROJECT,
                Decision.applies_to["project_id"].as_string() == project_id,
            )
        )
    if task_id:
        scope_conditions.append(
            and_(
                Decision.scope == DecisionScope.TASK,
                Decision.applies_to["task_id"].as_string() == task_id,
            )
        )
    if department:
        scope_conditions.append(
            and_(
                Decision.scope == DecisionScope.DEPARTMENT,
                Decision.applies_to["department"].as_string() == department,
            )
        )
    memory_query = (
        select(Memory)
        .where(Memory.tenant_id == tenant_id)
        .order_by(Memory.created_at.desc())
        .limit(per_section)
    )
    decision_query = (
        select(Decision)
        .where(
            Decision.tenant_id == tenant_id,
            Decision.status == DecisionStatus.ACTIVE,
            Decision.effective_at <= now,
            or_(Decision.expires_at.is_(None), Decision.expires_at > now),
            or_(*scope_conditions),
        )
        .order_by(Decision.effective_at.desc(), Decision.created_at.desc())
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
