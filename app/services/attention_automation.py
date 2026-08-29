import hashlib
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db import SessionLocal
from app.models import AttentionKind, AttentionLevel
from app.schemas import (
    AttentionAutomationItemRead,
    AttentionAutomationPolicyRead,
    AttentionAutomationRunRead,
    AttentionFollowUpCreate,
)
from app.services.attention import build_attention_queue
from app.services.attention_follow_ups import (
    AttentionFollowUpRejected,
    create_attention_follow_up,
)

RULE_VERSION = "attention-auto-plan-v1"
AUTOMATIC_KINDS = (
    AttentionKind.OVERDUE_COMMITMENT,
    AttentionKind.LONG_RUNNING_TASK,
    AttentionKind.TASK_FAILURE,
)
AUTOMATIC_LEVELS = (
    AttentionLevel.INFO,
    AttentionLevel.WATCH,
    AttentionLevel.ACTION,
)
MANUAL_KINDS = (
    AttentionKind.PENDING_APPROVAL,
    AttentionKind.DECISION_GOVERNANCE,
)
MANUAL_LEVELS = (
    AttentionLevel.DECISION,
    AttentionLevel.CRITICAL,
)


class AttentionAutomationRejected(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def attention_automation_policy(settings: Settings) -> AttentionAutomationPolicyRead:
    return AttentionAutomationPolicyRead(
        rule_version=RULE_VERSION,
        enabled=settings.attention_auto_plan_enabled,
        interval_seconds=settings.attention_auto_plan_interval_seconds,
        run_limit=settings.attention_auto_plan_limit,
        automatic_kinds=list(AUTOMATIC_KINDS),
        automatic_levels=list(AUTOMATIC_LEVELS),
        manual_kinds=list(MANUAL_KINDS),
        manual_levels=list(MANUAL_LEVELS),
        creates_task_execution=False,
        creates_external_action=False,
    )


def _idempotency_key(tenant_id: str, attention_id: str, fingerprint: str) -> str:
    digest = hashlib.sha256(f"{tenant_id}:{attention_id}:{fingerprint}".encode()).hexdigest()
    return f"attention-auto-plan:{digest}"


def _manual_reason(item) -> str | None:
    if item.kind in MANUAL_KINDS:
        return "requires_ceo_decision"
    if item.level in MANUAL_LEVELS:
        return "elevated_attention_level"
    if item.kind not in AUTOMATIC_KINDS or item.level not in AUTOMATIC_LEVELS:
        return "outside_automatic_policy"
    if item.follow_up_matches_current_signal:
        return "signal_already_planned"
    if item.acknowledged:
        return "signal_already_acknowledged"
    return None


async def run_attention_automation(
    session: AsyncSession,
    *,
    tenant_id: str,
    settings: Settings,
    dry_run: bool = True,
    limit: int | None = None,
    now: datetime | None = None,
    actor: str = "system:attention-auto-plan",
) -> AttentionAutomationRunRead:
    """Plan low-risk internal follow-ups. Never dispatch a task or external action."""

    if not dry_run and not settings.attention_auto_plan_enabled:
        raise AttentionAutomationRejected(
            "attention_auto_plan_disabled",
            "Attention automatic planning is disabled; use dry-run or enable it explicitly",
        )

    current = now or datetime.now(UTC)
    queue = await build_attention_queue(
        session,
        tenant_id,
        settings=settings,
        include_acknowledged=True,
        limit=None,
        now=current,
    )
    run_limit = limit or settings.attention_auto_plan_limit
    eligible_seen = 0
    created = 0
    output: list[AttentionAutomationItemRead] = []

    for item in queue.items:
        reason = _manual_reason(item)
        if reason is not None:
            output.append(
                AttentionAutomationItemRead(
                    attention_id=item.id,
                    fingerprint=item.fingerprint,
                    kind=item.kind,
                    level=item.level,
                    decision=(
                        "manual" if reason.startswith(("requires_", "elevated_")) else "skipped"
                    ),
                    reason=reason,
                    follow_up_id=item.follow_up_id,
                    task_id=item.follow_up_task_id,
                    commitment_id=item.follow_up_commitment_id,
                )
            )
            continue

        if eligible_seen >= run_limit:
            output.append(
                AttentionAutomationItemRead(
                    attention_id=item.id,
                    fingerprint=item.fingerprint,
                    kind=item.kind,
                    level=item.level,
                    decision="skipped",
                    reason="run_limit_reached",
                )
            )
            continue

        eligible_seen += 1
        if dry_run:
            output.append(
                AttentionAutomationItemRead(
                    attention_id=item.id,
                    fingerprint=item.fingerprint,
                    kind=item.kind,
                    level=item.level,
                    decision="eligible",
                    reason="low_risk_internal_signal",
                )
            )
            continue

        try:
            follow_up = await create_attention_follow_up(
                session,
                tenant_id=tenant_id,
                actor=actor,
                attention_id=item.id,
                payload=AttentionFollowUpCreate(
                    expected_fingerprint=item.fingerprint,
                    owner_id="chief_of_staff",
                    note=f"{RULE_VERSION}: 저위험 내부 신호 자동계획; 실행은 시작하지 않음",
                    idempotency_key=_idempotency_key(
                        tenant_id,
                        item.id,
                        item.fingerprint,
                    ),
                ),
                settings=settings,
                now=current,
            )
        except AttentionFollowUpRejected as exc:
            output.append(
                AttentionAutomationItemRead(
                    attention_id=item.id,
                    fingerprint=item.fingerprint,
                    kind=item.kind,
                    level=item.level,
                    decision="skipped",
                    reason=f"follow_up_rejected:{exc.code}",
                )
            )
            continue

        created += 1
        output.append(
            AttentionAutomationItemRead(
                attention_id=item.id,
                fingerprint=item.fingerprint,
                kind=item.kind,
                level=item.level,
                decision="created",
                reason="low_risk_internal_signal",
                follow_up_id=follow_up.id,
                task_id=follow_up.task_id,
                commitment_id=follow_up.commitment_id,
            )
        )

    skipped = len(output) - created - (eligible_seen if dry_run else 0)
    return AttentionAutomationRunRead(
        rule_version=RULE_VERSION,
        generated_at=current,
        enabled=settings.attention_auto_plan_enabled,
        dry_run=dry_run,
        scanned=len(queue.items),
        eligible=eligible_seen,
        created=created,
        skipped=skipped,
        items=output,
    )


async def dispatch_scheduled_attention_auto_plan(
    *,
    settings: Settings | None = None,
) -> AttentionAutomationRunRead:
    runtime_settings = settings or get_settings()
    if not runtime_settings.attention_auto_plan_enabled:
        return AttentionAutomationRunRead(
            rule_version=RULE_VERSION,
            generated_at=datetime.now(UTC),
            enabled=False,
            dry_run=False,
            scanned=0,
            eligible=0,
            created=0,
            skipped=0,
            items=[],
        )

    async with SessionLocal() as session:
        result = await run_attention_automation(
            session,
            tenant_id=runtime_settings.default_tenant_id,
            settings=runtime_settings,
            dry_run=False,
        )
        await session.commit()
        return result
