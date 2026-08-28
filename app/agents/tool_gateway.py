import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.agents.contracts import ResolvedTools, ToolAuthorization
from app.agents.definitions import AgentDefinition


class ToolRisk(StrEnum):
    READ_ONLY = "read_only"
    EXTERNAL_WRITE = "external_write"
    HIGH_IMPACT = "high_impact"


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    key: str
    purpose: str
    provider: str
    risk: ToolRisk
    required_permissions: tuple[str, ...]
    side_effects: bool = False
    approval_required: bool = False


class ToolPolicyError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def default_tool_catalog() -> tuple[ToolDescriptor, ...]:
    return (
        ToolDescriptor(
            key="web_search",
            purpose="Search public web sources for research evidence.",
            provider="openai",
            risk=ToolRisk.READ_ONLY,
            required_permissions=("web.search",),
        ),
    )


class OpenAIToolGateway:
    """Fail-closed policy gateway for tools exposed to the OpenAI runtime.

    V1 intentionally registers only public, read-only web search. Side-effecting tools
    require an immutable approval payload and execution ledger that are not enabled yet.
    """

    def __init__(
        self,
        *,
        catalog: Iterable[ToolDescriptor] | None = None,
        factories: dict[str, Callable[[], Any]] | None = None,
    ) -> None:
        descriptors = tuple(catalog or default_tool_catalog())
        self._catalog = {descriptor.key: descriptor for descriptor in descriptors}
        if len(self._catalog) != len(descriptors):
            raise ValueError("Tool catalog keys must be unique")
        self._factories = factories

    def catalog(self) -> tuple[ToolDescriptor, ...]:
        return tuple(self._catalog[key] for key in sorted(self._catalog))

    def _runtime_factories(self) -> dict[str, Callable[[], Any]]:
        if self._factories is not None:
            return self._factories
        from agents import WebSearchTool

        return {"web_search": WebSearchTool}

    def resolve_tools(self, definition: AgentDefinition) -> ResolvedTools:
        requested = definition.allowed_tools
        if len(set(requested)) != len(requested):
            raise ToolPolicyError("duplicate_tool", "Agent tool allowlist contains duplicates")

        factories = self._runtime_factories()
        runtime_tools: list[Any] = []
        authorizations: list[ToolAuthorization] = []
        permissions = set(definition.permissions)

        for tool_name in requested:
            descriptor = self._catalog.get(tool_name)
            if descriptor is None or tool_name not in factories:
                raise ToolPolicyError("unknown_tool", f"Tool '{tool_name}' is not registered")
            missing = set(descriptor.required_permissions) - permissions
            if missing:
                raise ToolPolicyError(
                    "permission_denied",
                    f"Agent '{definition.key}' lacks permission(s): {', '.join(sorted(missing))}",
                )
            if descriptor.side_effects or descriptor.risk != ToolRisk.READ_ONLY:
                raise ToolPolicyError(
                    "approval_context_required",
                    f"Tool '{tool_name}' cannot be exposed without an immutable approval context",
                )

            runtime_tools.append(factories[tool_name]())
            authorizations.append(
                ToolAuthorization(
                    tool_name=tool_name,
                    agent_key=definition.key,
                    risk=descriptor.risk.value,
                    required_permissions=descriptor.required_permissions,
                )
            )

        if authorizations:
            logging.getLogger("tool_gateway").info(
                "tool access authorized agent=%s tools=%s invocation_observed=false",
                definition.key,
                ",".join(item.tool_name for item in authorizations),
            )
        return ResolvedTools(tuple(runtime_tools), tuple(authorizations))


def public_tool_catalog() -> tuple[ToolDescriptor, ...]:
    return OpenAIToolGateway().catalog()
