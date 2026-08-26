from collections.abc import Sequence
from typing import Any

from app.agents.contracts import AgentRunResult, ModelProvider, RuntimeUsage, ToolProvider
from app.agents.definitions import AgentDefinition, ModelPolicy


class OpenAIModelProvider:
    provider_name = "openai"

    def resolve_model(self, policy: ModelPolicy) -> str:
        if policy.provider != self.provider_name:
            raise ValueError(f"OpenAI runtime cannot resolve provider '{policy.provider}'")
        return policy.model


class OpenAIToolProvider:
    def resolve_tools(self, tool_names: Sequence[str]) -> list[Any]:
        from agents import WebSearchTool

        factories = {"web_search": WebSearchTool}
        unknown = sorted(set(tool_names) - factories.keys())
        if unknown:
            raise ValueError(f"Unsupported OpenAI tool(s): {', '.join(unknown)}")
        return [factories[name]() for name in tool_names]


class OpenAIAgentsRuntime:
    """Adapter around the existing OpenAI Agents SDK Agent/Runner behavior."""

    name = "openai_agents"

    def __init__(
        self,
        model_provider: ModelProvider | None = None,
        tool_provider: ToolProvider | None = None,
        tracing_enabled: bool = False,
        api_key: str | None = None,
        store_responses: bool = False,
    ) -> None:
        from agents import set_default_openai_key, set_tracing_disabled

        set_tracing_disabled(not tracing_enabled)
        if api_key:
            set_default_openai_key(api_key, use_for_tracing=tracing_enabled)
        self.model_provider = model_provider or OpenAIModelProvider()
        self.tool_provider = tool_provider or OpenAIToolProvider()
        self.store_responses = store_responses

    async def run(self, definition: AgentDefinition, input_text: str) -> AgentRunResult:
        from agents import Agent, ModelSettings, Runner

        agent_kwargs: dict[str, Any] = {
            "name": definition.role,
            "instructions": definition.system_prompt,
            "model": self.model_provider.resolve_model(definition.model_policy),
            "tools": self.tool_provider.resolve_tools(definition.allowed_tools),
            "model_settings": ModelSettings(store=self.store_responses),
        }
        if definition.output_schema is not None:
            agent_kwargs["output_type"] = definition.output_schema

        run = await Runner.run(Agent(**agent_kwargs), input_text)
        usage = run.context_wrapper.usage
        return AgentRunResult(
            final_output=run.final_output,
            usage=RuntimeUsage(
                input_tokens=int(usage.input_tokens or 0),
                output_tokens=int(usage.output_tokens or 0),
                total_tokens=int(usage.total_tokens or 0),
            ),
        )
