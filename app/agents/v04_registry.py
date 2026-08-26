from app.agents.definitions import AgentDefinition, EvaluationStatus, ModelPolicy
from app.agents.outputs import ChiefOutput, ReviewerOutput
from app.agents.prompts import (
    CHIEF_INSTRUCTIONS,
    RESEARCH_INSTRUCTIONS,
    REVIEW_INSTRUCTIONS,
    STRATEGY_INSTRUCTIONS,
)
from app.agents.registry import AgentRegistry
from app.core.config import Settings

CHIEF_AGENT_KEY = "chief_of_staff"
RESEARCH_AGENT_KEY = "research"
STRATEGY_AGENT_KEY = "strategy"
REVIEWER_AGENT_KEY = "reviewer"


def build_v04_agent_registry(settings: Settings) -> AgentRegistry:
    """Express the existing V0.4 team as definitions without changing its workflow."""

    model_policy = ModelPolicy(
        provider="openai",
        model=settings.openai_model,
        capabilities=("text", "structured_output"),
    )
    shared = {
        "model_policy": model_policy,
        "memory_scope": ("company_context",),
        "knowledge_collections": ("memories", "decisions", "knowledge"),
        "workflow_templates": ("v0_4_fixed_orchestration",),
        "schedules": (),
        "working_environment": "openai_agents_hosted",
        "version": "0.4.0",
        "evaluation_status": EvaluationStatus.BASELINE,
    }
    return AgentRegistry(
        (
            AgentDefinition(
                key=CHIEF_AGENT_KEY,
                role="Chief of Staff",
                purpose="Synthesize specialist work into the final executive report.",
                system_prompt=CHIEF_INSTRUCTIONS,
                output_schema=ChiefOutput,
                allowed_tools=(),
                permissions=("knowledge.read", "approval.request"),
                approval_policy="propose_side_effects_for_ceo",
                **shared,
            ),
            AgentDefinition(
                key=RESEARCH_AGENT_KEY,
                role="Research Agent",
                purpose="Investigate the CEO request and produce a sourced research brief.",
                system_prompt=RESEARCH_INSTRUCTIONS,
                allowed_tools=("web_search",),
                permissions=("knowledge.read", "web.search"),
                **shared,
            ),
            AgentDefinition(
                key=STRATEGY_AGENT_KEY,
                role="Strategy Agent",
                purpose="Turn the CEO request into options and an executable strategy.",
                system_prompt=STRATEGY_INSTRUCTIONS,
                allowed_tools=(),
                permissions=("knowledge.read",),
                **shared,
            ),
            AgentDefinition(
                key=REVIEWER_AGENT_KEY,
                role="Reviewer Agent",
                purpose="Review the executive report and return PASS or REWORK feedback.",
                system_prompt=REVIEW_INSTRUCTIONS,
                output_schema=ReviewerOutput,
                allowed_tools=(),
                permissions=("knowledge.read",),
                **shared,
            ),
        )
    )
