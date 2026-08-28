from app.agents.definitions import AgentDefinition
from app.agents.operational_registry import build_operational_agent_registry
from app.core.config import Settings
from app.schemas import AgentDirectoryEntryRead


def public_agent_profile(definition: AgentDefinition) -> AgentDirectoryEntryRead:
    """Return declarative employee metadata without prompts or runtime objects."""

    return AgentDirectoryEntryRead(
        key=definition.key,
        role=definition.role,
        purpose=definition.purpose,
        provider=definition.model_policy.provider,
        model=definition.model_policy.model,
        capabilities=definition.model_policy.capabilities,
        memory_scope=definition.memory_scope,
        allowed_tools=definition.allowed_tools,
        permissions=definition.permissions,
        approval_policy=definition.approval_policy,
        knowledge_collections=definition.knowledge_collections,
        workflow_templates=definition.workflow_templates,
        schedules=definition.schedules,
        working_environment=definition.working_environment,
        version=definition.version,
        evaluation_status=definition.evaluation_status,
        structured_output=definition.output_schema is not None,
    )


def list_public_agent_profiles(settings: Settings) -> tuple[AgentDirectoryEntryRead, ...]:
    registry = build_operational_agent_registry(settings)
    return tuple(
        public_agent_profile(definition)
        for definition in sorted(registry.all(), key=lambda item: item.key)
    )


def get_public_agent_profile(settings: Settings, agent_key: str) -> AgentDirectoryEntryRead | None:
    definition = build_operational_agent_registry(settings).get(agent_key)
    return public_agent_profile(definition) if definition is not None else None
