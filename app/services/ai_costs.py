from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import RuntimeUsage
from app.core.config import Settings
from app.models import AICostLedgerEntry, AIMonthlyBudget, Delegation, TaskRun

MILLION = Decimal("1000000")
MONEY_QUANTUM = Decimal("0.00000001")
PRICING_SOURCE_URL = "https://developers.openai.com/api/docs/models/gpt-5.6-luna"


class AICostControlError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class ModelPricing:
    provider: str
    model: str
    version: str
    input_per_million_usd: Decimal
    cached_input_per_million_usd: Decimal
    output_per_million_usd: Decimal
    long_context_input_threshold: int
    long_context_input_multiplier: Decimal
    long_context_output_multiplier: Decimal
    source_url: str


GPT_5_6_LUNA_PRICING = ModelPricing(
    provider="openai",
    model="gpt-5.6-luna",
    version="openai-2026-08-28",
    input_per_million_usd=Decimal("0.20"),
    cached_input_per_million_usd=Decimal("0.02"),
    output_per_million_usd=Decimal("1.20"),
    long_context_input_threshold=272_000,
    long_context_input_multiplier=Decimal("2"),
    long_context_output_multiplier=Decimal("1.5"),
    source_url=PRICING_SOURCE_URL,
)

PRICING_CATALOG = {
    (GPT_5_6_LUNA_PRICING.provider, GPT_5_6_LUNA_PRICING.model): GPT_5_6_LUNA_PRICING
}


def _decimal(value: Decimal | float | int | str | None) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal | float | int | str | None) -> Decimal:
    return _decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_UP)


def require_model_pricing(provider: str, model: str) -> ModelPricing:
    pricing = PRICING_CATALOG.get((provider, model))
    if pricing is None:
        raise AICostControlError(
            "pricing_unavailable",
            f"No approved pricing snapshot exists for provider={provider}, model={model}",
        )
    return pricing


def estimate_max_cost_usd(pricing: ModelPricing, token_budget: int) -> Decimal:
    if token_budget < 0:
        raise ValueError("token_budget must be non-negative")
    if token_budget > pricing.long_context_input_threshold:
        highest_rate = max(
            pricing.input_per_million_usd * pricing.long_context_input_multiplier,
            pricing.output_per_million_usd * pricing.long_context_output_multiplier,
        )
    else:
        highest_rate = max(
            pricing.input_per_million_usd,
            pricing.output_per_million_usd,
        )
    return _money(_decimal(token_budget) * highest_rate / MILLION)


def estimate_usage_cost_usd(
    pricing: ModelPricing,
    *,
    input_tokens: int,
    output_tokens: int,
) -> tuple[Decimal, Decimal, Decimal]:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts must be non-negative")
    input_rate = pricing.input_per_million_usd
    output_rate = pricing.output_per_million_usd
    if input_tokens > pricing.long_context_input_threshold:
        input_rate *= pricing.long_context_input_multiplier
        output_rate *= pricing.long_context_output_multiplier
    estimated_cost = (
        _decimal(input_tokens) * input_rate + _decimal(output_tokens) * output_rate
    ) / MILLION
    return _money(estimated_cost), input_rate, output_rate


def price_delegation(delegation: Delegation) -> ModelPricing:
    provider = str(delegation.policy_snapshot.get("provider") or delegation.provider or "")
    model = str(delegation.policy_snapshot.get("model") or delegation.model or "")
    pricing = require_model_pricing(provider, model)
    if delegation.pricing_version not in {None, pricing.version}:
        raise AICostControlError(
            "pricing_version_mismatch",
            "Delegation pricing snapshot no longer matches the approved catalog",
        )
    delegation.pricing_version = pricing.version
    delegation.estimated_max_cost_usd = estimate_max_cost_usd(pricing, delegation.token_budget)
    return pricing


def validate_delegation_cost_ceiling(delegation: Delegation) -> ModelPricing:
    pricing = price_delegation(delegation)
    if _decimal(delegation.estimated_max_cost_usd) > _decimal(delegation.cost_budget_usd):
        raise AICostControlError(
            "cost_budget_too_small",
            "Delegation cost budget is below the conservative token-budget estimate",
        )
    return pricing


def current_period_start(now: datetime | None = None) -> date:
    current = now or datetime.now(UTC)
    return date(current.year, current.month, 1)


async def _locked_monthly_budget(
    session: AsyncSession,
    *,
    tenant_id: str,
    provider: str,
    period_start: date,
    configured_budget: Decimal,
) -> AIMonthlyBudget:
    query = select(AIMonthlyBudget).where(
        AIMonthlyBudget.tenant_id == tenant_id,
        AIMonthlyBudget.provider == provider,
        AIMonthlyBudget.period_start == period_start,
    )
    budget = await session.scalar(query.with_for_update())
    if budget is None:
        try:
            async with session.begin_nested():
                session.add(
                    AIMonthlyBudget(
                        tenant_id=tenant_id,
                        provider=provider,
                        period_start=period_start,
                        budget_usd=configured_budget,
                        reserved_usd=0,
                        estimated_spend_usd=0,
                        uncertain_spend_usd=0,
                    )
                )
                await session.flush()
        except IntegrityError:
            pass
        budget = await session.scalar(query.with_for_update())
    if budget is None:
        raise RuntimeError("Unable to initialize monthly AI budget")
    budget.budget_usd = configured_budget
    return budget


async def reserve_delegation_cost(
    session: AsyncSession,
    delegation: Delegation,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> Decimal:
    pricing = validate_delegation_cost_ceiling(delegation)
    existing_reservation = _decimal(delegation.reserved_cost_usd)
    if existing_reservation > 0:
        return existing_reservation
    reservation = _money(delegation.estimated_max_cost_usd)
    period = current_period_start(now)
    budget = await _locked_monthly_budget(
        session,
        tenant_id=delegation.tenant_id,
        provider=pricing.provider,
        period_start=period,
        configured_budget=_money(settings.openai_monthly_budget_usd),
    )
    committed = (
        _decimal(budget.reserved_usd)
        + _decimal(budget.estimated_spend_usd)
        + _decimal(budget.uncertain_spend_usd)
    )
    if committed + reservation > _decimal(budget.budget_usd):
        remaining = max(Decimal("0"), _decimal(budget.budget_usd) - committed)
        raise AICostControlError(
            "monthly_budget_exceeded",
            "Monthly OpenAI budget cannot reserve this execution "
            f"(required=${reservation:.8f}, remaining=${remaining:.8f})",
        )
    budget.reserved_usd = _money(_decimal(budget.reserved_usd) + reservation)
    delegation.reserved_cost_usd = reservation
    delegation.cost_reservation_period_start = period
    return reservation


async def release_delegation_cost_reservation(
    session: AsyncSession,
    delegation: Delegation,
    settings: Settings,
) -> Decimal:
    reservation = _money(delegation.reserved_cost_usd)
    period = delegation.cost_reservation_period_start
    if reservation <= 0 or period is None:
        delegation.reserved_cost_usd = Decimal("0")
        delegation.cost_reservation_period_start = None
        return Decimal("0")
    pricing = price_delegation(delegation)
    budget = await _locked_monthly_budget(
        session,
        tenant_id=delegation.tenant_id,
        provider=pricing.provider,
        period_start=period,
        configured_budget=_money(settings.openai_monthly_budget_usd),
    )
    budget.reserved_usd = _money(max(Decimal("0"), _decimal(budget.reserved_usd) - reservation))
    delegation.reserved_cost_usd = Decimal("0")
    delegation.cost_reservation_period_start = None
    return reservation


async def finalize_delegation_cost(
    session: AsyncSession,
    delegation: Delegation,
    task_run: TaskRun,
    settings: Settings,
    *,
    usage: RuntimeUsage | None,
    execution_succeeded: bool,
    now: datetime | None = None,
) -> AICostLedgerEntry:
    existing = await session.scalar(
        select(AICostLedgerEntry).where(AICostLedgerEntry.task_run_id == task_run.id)
    )
    if existing is not None:
        return existing
    pricing = price_delegation(delegation)
    reservation = await release_delegation_cost_reservation(session, delegation, settings)
    if usage is None:
        estimated_cost = reservation
        input_tokens = output_tokens = total_tokens = 0
        input_rate = pricing.input_per_million_usd
        output_rate = pricing.output_per_million_usd
        calculation_status = "uncertain_upper_bound"
    else:
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        total_tokens = usage.total_tokens
        estimated_cost, input_rate, output_rate = estimate_usage_cost_usd(
            pricing,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        calculation_status = (
            "token_estimate_completed" if execution_succeeded else "token_estimate_failed"
        )
    period = current_period_start(now)
    budget = await _locked_monthly_budget(
        session,
        tenant_id=delegation.tenant_id,
        provider=pricing.provider,
        period_start=period,
        configured_budget=_money(settings.openai_monthly_budget_usd),
    )
    if calculation_status == "uncertain_upper_bound":
        budget.uncertain_spend_usd = _money(_decimal(budget.uncertain_spend_usd) + estimated_cost)
    else:
        budget.estimated_spend_usd = _money(_decimal(budget.estimated_spend_usd) + estimated_cost)
    delegation.actual_estimated_cost_usd = estimated_cost
    entry = AICostLedgerEntry(
        tenant_id=delegation.tenant_id,
        delegation_id=delegation.id,
        task_run_id=task_run.id,
        provider=pricing.provider,
        model=pricing.model,
        pricing_version=pricing.version,
        calculation_status=calculation_status,
        currency="USD",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        input_rate_per_million_usd=input_rate,
        output_rate_per_million_usd=output_rate,
        estimated_cost_usd=estimated_cost,
        provider_billed_cost_usd=None,
        occurred_at=now or datetime.now(UTC),
    )
    session.add(entry)
    await session.flush()
    return entry


async def get_current_month_cost_summary(
    session: AsyncSession,
    *,
    tenant_id: str,
    settings: Settings,
    now: datetime | None = None,
) -> dict[str, object]:
    period = current_period_start(now)
    budget = await session.scalar(
        select(AIMonthlyBudget).where(
            AIMonthlyBudget.tenant_id == tenant_id,
            AIMonthlyBudget.provider == "openai",
            AIMonthlyBudget.period_start == period,
        )
    )
    budget_usd = _money(
        budget.budget_usd if budget is not None else settings.openai_monthly_budget_usd
    )
    reserved = _money(budget.reserved_usd if budget is not None else 0)
    estimated = _money(budget.estimated_spend_usd if budget is not None else 0)
    uncertain = _money(budget.uncertain_spend_usd if budget is not None else 0)
    committed = _money(reserved + estimated + uncertain)
    return {
        "tenant_id": tenant_id,
        "provider": "openai",
        "period_start": period,
        "currency": "USD",
        "budget_usd": budget_usd,
        "reserved_usd": reserved,
        "estimated_spend_usd": estimated,
        "uncertain_spend_usd": uncertain,
        "remaining_usd": _money(max(Decimal("0"), budget_usd - committed)),
        "pricing_is_estimate": True,
    }
