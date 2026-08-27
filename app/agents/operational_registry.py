from app.agents.definitions import AgentDefinition, EvaluationStatus, ModelPolicy
from app.agents.prompts import LEGAL_REVIEW_INSTRUCTIONS, MARKETING_INSTRUCTIONS
from app.agents.registry import AgentRegistry
from app.agents.v04_registry import build_v04_agent_registry
from app.core.config import Settings

MARKETING_AGENT_KEY = "marketing"
LEGAL_REVIEW_AGENT_KEY = "legal_review"


def build_operational_agent_registry(settings: Settings) -> AgentRegistry:
    """Add opt-in specialists while preserving every V0.4 agent definition."""

    definitions = list(build_v04_agent_registry(settings).all())
    model_policy = ModelPolicy(
        provider="openai",
        model=settings.openai_model,
        capabilities=("text",),
    )
    shared = {
        "model_policy": model_policy,
        "memory_scope": ("company_context",),
        "knowledge_collections": ("memories", "decisions", "knowledge"),
        "working_environment": "openai_agents_hosted",
        "version": "0.5.0",
        "evaluation_status": EvaluationStatus.UNTESTED,
    }
    definitions.extend(
        (
            AgentDefinition(
                key=MARKETING_AGENT_KEY,
                role="Marketing Agent",
                purpose="Produce evidence-grounded marketing drafts and campaign proposals.",
                system_prompt=MARKETING_INSTRUCTIONS,
                allowed_tools=(),
                permissions=("knowledge.read",),
                approval_policy="draft_only_external_publish_requires_ceo",
                workflow_templates=("v0_4_marketing_extension",),
                schedules=(),
                **shared,
            ),
            AgentDefinition(
                key=LEGAL_REVIEW_AGENT_KEY,
                role="Legal Risk Review Agent",
                purpose="Identify preliminary legal and regulatory risks for CEO review.",
                system_prompt=LEGAL_REVIEW_INSTRUCTIONS,
                allowed_tools=(),
                permissions=("knowledge.read",),
                approval_policy="advisory_only_no_legal_action",
                workflow_templates=("v0_4_legal_review_extension",),
                schedules=(),
                **shared,
            ),
        )
    )
    return AgentRegistry(definitions)
