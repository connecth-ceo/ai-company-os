from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EvaluationStatus(StrEnum):
    UNTESTED = "untested"
    BASELINE = "baseline"
    VALIDATED = "validated"
    DEPRECATED = "deprecated"


class ModelPolicy(BaseModel):
    """Provider-neutral model selection metadata.

    Phase 1 stores the currently configured provider/model without implementing routing,
    fallbacks, budgets, or provider health checks.
    """

    model_config = ConfigDict(frozen=True)

    provider: str = "openai"
    model: str
    capabilities: tuple[str, ...] = ()


class AgentDefinition(BaseModel):
    """Versioned description of an AI employee, independent from its runtime.

    Most fields are declarative extension points in Phase 1. Runtime behavior remains the
    V0.4 fixed orchestration until later migration phases.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    role: str
    purpose: str
    system_prompt: str
    output_schema: type[BaseModel] | None = Field(default=None, exclude=True)
    model_policy: ModelPolicy
    memory_scope: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    approval_policy: str = "none"
    knowledge_collections: tuple[str, ...] = ()
    workflow_templates: tuple[str, ...] = ()
    schedules: tuple[str, ...] = ()
    working_environment: str = "default"
    version: str = "0.1.0"
    evaluation_status: EvaluationStatus = EvaluationStatus.UNTESTED
