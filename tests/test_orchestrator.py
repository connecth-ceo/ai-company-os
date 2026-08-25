import pytest

from app.agents.orchestrator import orchestrate
from app.core.config import Settings
from app.models import ReviewVerdict


@pytest.mark.asyncio
async def test_mock_orchestration_has_all_roles_outputs():
    result = await orchestrate("경쟁사 조사 후 실행 전략을 만들어줘.", Settings(ai_provider="mock"))

    assert result.research
    assert result.strategy
    assert result.final_report
    assert result.verdict == ReviewVerdict.PASS


@pytest.mark.asyncio
async def test_mock_orchestration_exposes_context_and_approval_requests():
    result = await orchestrate(
        "보고서를 외부 채널에 게시해줘.",
        Settings(ai_provider="mock"),
        "COMPANY MEMORIES:\n- [tone] 결론부터 보고한다.",
    )

    assert result.company_context_used is True
    assert result.approval_requests[0].risk == "high"
    assert result.artifacts()["approval_requests"][0]["action"]
