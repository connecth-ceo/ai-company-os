from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.agents.definitions import AgentDefinition, ModelPolicy


@dataclass(frozen=True, slots=True)
class RuntimeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    final_output: Any
    usage: RuntimeUsage = RuntimeUsage()


@runtime_checkable
class AgentRuntime(Protocol):
    """Executes one AgentDefinition without owning the company workflow."""

    name: str

    async def run(
        self,
        definition: AgentDefinition,
        input_text: str,
        *,
        max_output_tokens: int | None = None,
    ) -> AgentRunResult: ...


@runtime_checkable
class ModelProvider(Protocol):
    """Resolves a provider-neutral policy to a runtime model identifier."""

    provider_name: str

    def resolve_model(self, policy: ModelPolicy) -> str: ...


@runtime_checkable
class ToolProvider(Protocol):
    """Resolves allowlisted tool names for a specific runtime."""

    def resolve_tools(self, tool_names: Sequence[str]) -> list[Any]: ...


@runtime_checkable
class KnowledgeRetriever(Protocol):
    """Future Knowledge V2 retrieval boundary; no new retrieval engine in Phase 1."""

    async def retrieve(
        self,
        query: str,
        *,
        tenant_id: str,
        collections: Sequence[str] = (),
    ) -> str: ...
