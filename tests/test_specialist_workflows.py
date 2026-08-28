from datetime import UTC, datetime

import pytest

from app.agents.contracts import AgentRunResult, RuntimeUsage
from app.agents.operational_registry import (
    LEGAL_REVIEW_AGENT_KEY,
    MARKETING_AGENT_KEY,
    build_operational_agent_registry,
)
from app.agents.orchestrator import explicit_workflow, orchestrate
from app.agents.outputs import ChiefOutput, ReviewerOutput
from app.agents.v04_registry import (
    CHIEF_AGENT_KEY,
    RESEARCH_AGENT_KEY,
    REVIEWER_AGENT_KEY,
    STRATEGY_AGENT_KEY,
)
from app.core.config import Settings
from app.db import SessionLocal
from app.models import Approval, Commitment, ReviewVerdict, Task, TaskStatus
from app.services.daily_briefing import build_daily_briefing


def test_operational_registry_extends_without_replacing_v04_team():
    registry = build_operational_agent_registry(Settings(ai_provider="mock"))

    assert {definition.key for definition in registry.all()} == {
        CHIEF_AGENT_KEY,
        RESEARCH_AGENT_KEY,
        STRATEGY_AGENT_KEY,
        REVIEWER_AGENT_KEY,
        MARKETING_AGENT_KEY,
        LEGAL_REVIEW_AGENT_KEY,
    }
    assert registry.require(MARKETING_AGENT_KEY).approval_policy == (
        "draft_only_external_publish_requires_ceo"
    )
    assert registry.require(LEGAL_REVIEW_AGENT_KEY).approval_policy == (
        "advisory_only_no_legal_action"
    )


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("일반 시장조사", "default"),
        ("/marketing 신제품 소개문", MARKETING_AGENT_KEY),
        ("/마케팅 신제품 소개문", MARKETING_AGENT_KEY),
        ("/legal 계약서 위험 검토", LEGAL_REVIEW_AGENT_KEY),
        ("/법률 개인정보 위험 검토", LEGAL_REVIEW_AGENT_KEY),
    ],
)
def test_only_explicit_commands_select_specialist(input_text, expected):
    assert explicit_workflow(input_text) == expected


@pytest.mark.asyncio
async def test_mock_specialist_workflows_are_labeled_and_auditable():
    settings = Settings(ai_provider="mock")

    marketing = await orchestrate("/marketing 신제품 소개문", settings)
    legal = await orchestrate("/legal 개인정보 위험 검토", settings)

    assert marketing.workflow == MARKETING_AGENT_KEY
    assert "Marketing Draft" in marketing.specialist_brief
    assert marketing.artifacts()["workflow"] == MARKETING_AGENT_KEY
    assert legal.workflow == LEGAL_REVIEW_AGENT_KEY
    assert "법률 자문이 아닙니다" in legal.specialist_brief


class SpecialistRuntime:
    name = "specialist_test_runtime"

    def __init__(self):
        self.calls = []
        self.inputs = []

    async def run(self, definition, input_text):
        self.calls.append(definition.key)
        self.inputs.append((definition.key, input_text))
        if definition.key == CHIEF_AGENT_KEY:
            output = ChiefOutput(final_report="법률 위험 예비 검토이며 법률 자문이 아닙니다.")
        elif definition.key == REVIEWER_AGENT_KEY:
            output = ReviewerOutput(verdict=ReviewVerdict.PASS, feedback="ready")
        else:
            output = f"{definition.key} brief"
        return AgentRunResult(
            final_output=output,
            usage=RuntimeUsage(input_tokens=1, output_tokens=1, total_tokens=2),
        )


@pytest.mark.asyncio
async def test_openai_path_adds_specialist_inside_existing_control_plane():
    runtime = SpecialistRuntime()
    result = await orchestrate(
        "/legal 개인정보 위험 검토",
        Settings(ai_provider="openai", openai_api_key="test-key"),
        runtime=runtime,
    )

    assert runtime.calls == [
        RESEARCH_AGENT_KEY,
        STRATEGY_AGENT_KEY,
        LEGAL_REVIEW_AGENT_KEY,
        CHIEF_AGENT_KEY,
        REVIEWER_AGENT_KEY,
    ]
    assert result.workflow == LEGAL_REVIEW_AGENT_KEY
    assert result.total_tokens == 10
    chief_input = next(text for key, text in runtime.inputs if key == CHIEF_AGENT_KEY)
    reviewer_input = next(text for key, text in runtime.inputs if key == REVIEWER_AGENT_KEY)
    assert "SPECIALIST BRIEF" in chief_input
    assert "not legal advice" in chief_input
    assert "not legal advice" in reviewer_input


@pytest.mark.asyncio
async def test_daily_briefing_is_read_only_database_summary():
    async with SessionLocal() as session:
        session.add_all(
            (
                Task(
                    tenant_id="owner",
                    title="완료 업무",
                    request="done",
                    status=TaskStatus.COMPLETED,
                ),
                Task(
                    tenant_id="owner",
                    title="진행 업무",
                    request="running",
                    status=TaskStatus.RUNNING,
                ),
                Approval(
                    tenant_id="owner",
                    action="외부 게시",
                    reason="대표 승인 필요",
                ),
                Commitment(
                    tenant_id="owner",
                    statement="고객에게 후속 연락",
                    owner_type="person",
                    owner_id="CEO",
                    due_at=datetime(2026, 8, 26, 23, 0, tzinfo=UTC),
                    status="open",
                    source_type="manual",
                ),
            )
        )
        await session.commit()

        briefing = await build_daily_briefing(
            session,
            "owner",
            now=datetime(2026, 8, 27, 0, 0, tzinfo=UTC),
        )

    assert "2026-08-27 09:00 KST" in briefing
    assert "완료 1건" in briefing
    assert "진행/대기 1건" in briefing
    assert "승인 대기 1건" in briefing
    assert "약속 지연 1건" in briefing
    assert "고객에게 후속 연락" in briefing
    assert "완료 업무" in briefing
