import asyncio
from decimal import Decimal

from app.agents.contracts import AgentRunResult, RuntimeUsage
from app.core.config import Settings, get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Delegation
from app.services.ai_costs import (
    GPT_5_6_LUNA_PRICING,
    estimate_max_cost_usd,
    estimate_usage_cost_usd,
)
from app.services.delegation_execution import dispatch_delegation, execute_delegation


def _create_delegation(
    client,
    *,
    token_budget: int = 2_000,
    cost_budget_usd: float = 0.5,
):
    parent = client.post(
        "/api/v1/tasks",
        json={"title": "Cost parent", "request": "비용 통제 검증"},
    ).json()
    response = client.post(
        f"/api/v1/tasks/{parent['id']}/delegations",
        json={
            "title": "Cost child",
            "request": "짧은 비용 검증 결과를 작성해줘",
            "delegated_role": "research",
            "reason": "cost ledger test",
            "token_budget": token_budget,
            "timeout_seconds": 60,
            "cost_budget_usd": cost_budget_usd,
        },
    )
    return response


def test_luna_pricing_snapshot_and_paid_smoke_estimate():
    pricing = GPT_5_6_LUNA_PRICING

    cost, input_rate, output_rate = estimate_usage_cost_usd(
        pricing,
        input_tokens=1_554,
        output_tokens=306,
    )

    assert pricing.source_url.endswith("/models/gpt-5.6-luna")
    assert input_rate == Decimal("0.20")
    assert output_rate == Decimal("1.20")
    assert cost == Decimal("0.00067800")
    assert estimate_max_cost_usd(pricing, 2_000) == Decimal("0.00240000")


def test_delegation_rejects_cost_ceiling_below_token_estimate(client):
    response = _create_delegation(
        client,
        token_budget=10_000,
        cost_budget_usd=0.001,
    )

    assert response.status_code == 409
    assert "conservative estimate" in response.json()["detail"]


def test_execution_writes_immutable_estimate_and_monthly_summary(client):
    created = _create_delegation(client).json()

    class PaidUsageRuntime:
        name = "paid_usage_test"

        async def run(self, definition, input_text, *, max_output_tokens=None):
            del definition, input_text, max_output_tokens
            return AgentRunResult(
                final_output="cost ledger complete",
                usage=RuntimeUsage(input_tokens=1_554, output_tokens=306, total_tokens=1_860),
            )

    async def execute() -> None:
        settings = Settings(ai_provider="mock")
        async with SessionLocal() as session:
            delegation = await session.get(Delegation, created["id"])
            await dispatch_delegation(session, delegation, settings, actor="test")
        async with SessionLocal() as session:
            await execute_delegation(
                session,
                created["id"],
                runtime=PaidUsageRuntime(),
                raise_on_failure=True,
            )

    asyncio.run(execute())
    detail = client.get(f"/api/v1/delegations/{created['id']}").json()
    ledger = client.get("/api/v1/ai-costs/ledger").json()
    summary = client.get("/api/v1/ai-costs/current-month").json()

    assert detail["pricing_version"] == "openai-2026-08-28"
    assert detail["estimated_max_cost_usd"] == 0.0024
    assert detail["reserved_cost_usd"] == 0
    assert detail["actual_estimated_cost_usd"] == 0.000678
    assert len(ledger) == 1
    assert ledger[0]["delegation_id"] == created["id"]
    assert ledger[0]["calculation_status"] == "token_estimate_completed"
    assert ledger[0]["provider_billed_cost_usd"] is None
    assert ledger[0]["estimated_cost_usd"] == 0.000678
    assert summary["reserved_usd"] == 0
    assert summary["estimated_spend_usd"] == 0.000678
    assert summary["uncertain_spend_usd"] == 0
    assert summary["pricing_is_estimate"] is True
    assert client.get("/api/v1/ai-costs/ledger", headers={"X-Tenant-ID": "other"}).json() == []
    other_summary = client.get(
        "/api/v1/ai-costs/current-month", headers={"X-Tenant-ID": "other"}
    ).json()
    assert other_summary["estimated_spend_usd"] == 0
    assert other_summary["uncertain_spend_usd"] == 0


def test_monthly_budget_blocks_dispatch_before_provider_call(client):
    constrained = Settings(ai_provider="mock", openai_monthly_budget_usd=0.001)
    app.dependency_overrides[get_settings] = lambda: constrained
    try:
        created = _create_delegation(client).json()
        response = client.post(f"/api/v1/delegations/{created['id']}/run")
        detail = client.get(f"/api/v1/delegations/{created['id']}").json()
        summary = client.get("/api/v1/ai-costs/current-month").json()
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 409
    assert "Monthly OpenAI budget" in response.json()["detail"]
    assert detail["status"] == "created"
    assert detail["reserved_cost_usd"] == 0
    assert summary["budget_usd"] == 0.001
    assert summary["remaining_usd"] == 0.001
