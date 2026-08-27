import asyncio

import pytest

from app.agents.contracts import AgentRunResult, RuntimeUsage
from app.agents.definitions import AgentDefinition, EvaluationStatus, ModelPolicy
from app.agents.orchestrator import orchestrate
from app.agents.outputs import ApprovalRequest, ChiefOutput, ReviewerOutput
from app.agents.prompts import CHIEF_INSTRUCTIONS, RESEARCH_INSTRUCTIONS, STRATEGY_INSTRUCTIONS
from app.agents.registry import AgentRegistry, DuplicateAgentError, UnknownAgentError
from app.agents.runtimes import OpenAIAgentsRuntime
from app.agents.v04_registry import (
    CHIEF_AGENT_KEY,
    RESEARCH_AGENT_KEY,
    REVIEWER_AGENT_KEY,
    STRATEGY_AGENT_KEY,
    build_v04_agent_registry,
)
from app.core.config import Settings
from app.models import ReviewVerdict


def test_v04_registry_expresses_existing_team_and_future_boundaries():
    registry = build_v04_agent_registry(Settings(ai_provider="mock"))

    assert {definition.key for definition in registry.all()} == {
        CHIEF_AGENT_KEY,
        RESEARCH_AGENT_KEY,
        STRATEGY_AGENT_KEY,
        REVIEWER_AGENT_KEY,
    }
    research = registry.require(RESEARCH_AGENT_KEY)
    chief = registry.require(CHIEF_AGENT_KEY)
    reviewer = registry.require(REVIEWER_AGENT_KEY)

    assert research.allowed_tools == ("web_search",)
    assert research.model_policy.provider == "openai"
    assert research.memory_scope == ("company_context",)
    assert research.knowledge_collections
    assert research.workflow_templates == ("v0_4_fixed_orchestration",)
    assert research.schedules == ()
    assert research.version == "0.4.0"
    assert research.evaluation_status == EvaluationStatus.BASELINE
    assert chief.output_schema is ChiefOutput
    assert chief.approval_policy == "propose_side_effects_for_ceo"
    assert reviewer.output_schema is ReviewerOutput


def test_prompts_require_segment_specific_evidence():
    compact_chief = " ".join(CHIEF_INSTRUCTIONS.lower().split())
    assert "every type-and-problem pairing" in RESEARCH_INSTRUCTIONS
    assert "broad survey" in RESEARCH_INSTRUCTIONS
    assert "more specific segment" in RESEARCH_INSTRUCTIONS
    assert "segment-specific evidence" in STRATEGY_INSTRUCTIONS
    assert "generic source plus a hypothesis label" in compact_chief
    assert "does not satisfy a request" in compact_chief


def test_registry_rejects_duplicates_and_missing_agents():
    definition = AgentDefinition(
        key="sample",
        role="Sample",
        purpose="Test registry behavior.",
        system_prompt="Return a sample response.",
        model_policy=ModelPolicy(provider="openai", model="test-model"),
    )
    registry = AgentRegistry((definition,))

    with pytest.raises(DuplicateAgentError):
        registry.register(definition)
    with pytest.raises(UnknownAgentError):
        registry.require("missing")


@pytest.mark.asyncio
async def test_openai_runtime_adapts_agent_runner_and_tools(monkeypatch):
    captured: dict[str, object] = {}

    class FakeWebSearchTool:
        pass

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class FakeUsage:
        input_tokens = 2
        output_tokens = 3
        total_tokens = 5

    class FakeContextWrapper:
        usage = FakeUsage()

    class FakeRun:
        final_output = "adapter result"
        context_wrapper = FakeContextWrapper()

    class FakeRunner:
        @staticmethod
        async def run(agent, input_text):
            captured["agent"] = agent
            captured["input_text"] = input_text
            return FakeRun()

    import agents

    monkeypatch.setattr(agents, "Agent", FakeAgent)
    monkeypatch.setattr(agents, "Runner", FakeRunner)
    monkeypatch.setattr(agents, "WebSearchTool", FakeWebSearchTool)
    monkeypatch.setattr(
        agents,
        "set_tracing_disabled",
        lambda disabled: captured.update({"tracing_disabled": disabled}),
    )
    monkeypatch.setattr(
        agents,
        "set_default_openai_key",
        lambda key, use_for_tracing: captured.update(
            {"api_key": key, "key_used_for_tracing": use_for_tracing}
        ),
    )

    definition = build_v04_agent_registry(Settings(ai_provider="mock")).require(RESEARCH_AGENT_KEY)
    result = await OpenAIAgentsRuntime(api_key="runtime-key").run(definition, "CEO request")

    assert result.final_output == "adapter result"
    assert result.usage == RuntimeUsage(input_tokens=2, output_tokens=3, total_tokens=5)
    assert captured["name"] == "Research Agent"
    assert captured["model"] == definition.model_policy.model
    assert isinstance(captured["tools"][0], FakeWebSearchTool)
    assert captured["input_text"] == "CEO request"
    assert captured["tracing_disabled"] is True
    assert captured["api_key"] == "runtime-key"
    assert captured["key_used_for_tracing"] is False
    assert captured["model_settings"].store is False


class ScriptedRuntime:
    name = "scripted_test_runtime"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.inputs: list[tuple[str, str]] = []
        self.active = 0
        self.max_active = 0
        self.chief_calls = 0
        self.review_calls = 0

    async def run(self, definition, input_text):
        self.calls.append(definition.key)
        self.inputs.append((definition.key, input_text))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0)
        self.active -= 1

        if definition.key == RESEARCH_AGENT_KEY:
            output = "research result"
        elif definition.key == STRATEGY_AGENT_KEY:
            output = "strategy result"
        elif definition.key == CHIEF_AGENT_KEY:
            self.chief_calls += 1
            output = ChiefOutput(
                final_report=("draft report" if self.chief_calls == 1 else "reworked final report"),
                approval_requests=(
                    []
                    if self.chief_calls == 1
                    else [
                        ApprovalRequest(
                            action="external publish",
                            reason="CEO approval required",
                            risk="high",
                        )
                    ]
                ),
            )
        else:
            self.review_calls += 1
            output = ReviewerOutput(
                verdict=(ReviewVerdict.REWORK if self.review_calls == 1 else ReviewVerdict.PASS),
                feedback="revise" if self.review_calls == 1 else "ready",
            )
        return AgentRunResult(
            final_output=output,
            usage=RuntimeUsage(input_tokens=1, output_tokens=2, total_tokens=3),
        )


@pytest.mark.asyncio
async def test_fixed_orchestrator_uses_runtime_boundary_and_preserves_rework():
    settings = Settings(
        ai_provider="openai",
        openai_api_key="x",
        review_max_reworks=1,
    )
    runtime = ScriptedRuntime()
    registry = build_v04_agent_registry(settings)

    result = await orchestrate(
        "test request",
        settings,
        "company context",
        runtime=runtime,
        registry=registry,
    )

    assert runtime.max_active == 2
    assert runtime.calls[:2] == [RESEARCH_AGENT_KEY, STRATEGY_AGENT_KEY]
    assert runtime.chief_calls == 2
    assert runtime.review_calls == 2
    assert result.final_report == "reworked final report"
    assert result.verdict == ReviewVerdict.PASS
    assert result.rework_count == 1
    assert result.approval_requests[0].risk == "high"
    assert result.input_tokens == 6
    assert result.output_tokens == 12
    assert result.total_tokens == 18
    assert result.company_context_used is True
    chief_inputs = [text for key, text in runtime.inputs if key == CHIEF_AGENT_KEY]
    assert len(chief_inputs) == 2
    assert "CEO REQUEST:\ntest request" in chief_inputs[1]
    assert "RESEARCH BRIEF:\nresearch result" in chief_inputs[1]
    assert "STRATEGY BRIEF:\nstrategy result" in chief_inputs[1]
    assert "REVIEW FEEDBACK:\nrevise" in chief_inputs[1]
