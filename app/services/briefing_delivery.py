import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, get_settings
from app.db import SessionLocal
from app.models import BriefingDelivery, BriefingDeliveryStatus
from app.services.audit import add_audit_event
from app.services.daily_briefing import build_daily_briefing
from app.services.telegram import send_telegram_message

DeliverySender = Callable[[Settings, str, str], Awaitable[bool]]


class BriefingDispatchOutcome(StrEnum):
    DISABLED = "disabled"
    NOT_DUE = "not_due"
    QUIET_HOURS = "quiet_hours"
    SENT = "sent"
    ALREADY_SENT = "already_sent"
    BUSY = "busy"
    RETRY_PENDING = "retry_pending"
    EXHAUSTED = "exhausted"
    MANUAL_REVIEW = "manual_review"
    FAILED = "failed"


@dataclass(frozen=True)
class BriefingDispatchResult:
    outcome: BriefingDispatchOutcome
    delivery_id: str | None = None
    attempt_count: int = 0


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_quiet_hour(local_hour: int, settings: Settings) -> bool:
    start = settings.briefing_quiet_start_hour
    end = settings.briefing_quiet_end_hour
    if start < end:
        return start <= local_hour < end
    return local_hour >= start or local_hour < end


def _scheduled_window(
    current: datetime,
    settings: Settings,
) -> tuple[date, datetime] | BriefingDispatchOutcome:
    local_now = as_utc(current).astimezone(ZoneInfo(settings.briefing_timezone))
    if _is_quiet_hour(local_now.hour, settings):
        return BriefingDispatchOutcome.QUIET_HOURS
    scheduled_local = datetime.combine(
        local_now.date(),
        time(settings.briefing_hour, settings.briefing_minute),
        tzinfo=local_now.tzinfo,
    )
    if (
        not scheduled_local
        <= local_now
        < scheduled_local + timedelta(hours=settings.briefing_catchup_hours)
    ):
        return BriefingDispatchOutcome.NOT_DUE
    return local_now.date(), scheduled_local.astimezone(UTC)


async def _get_or_create_delivery(
    *,
    tenant_id: str,
    briefing_date: date,
    destination: str,
    scheduled_for: datetime,
) -> BriefingDelivery:
    dedupe_key = f"daily-briefing:{tenant_id}:{briefing_date.isoformat()}:telegram"
    async with SessionLocal() as session:
        existing = (
            await session.scalars(
                select(BriefingDelivery).where(BriefingDelivery.dedupe_key == dedupe_key)
            )
        ).first()
        if existing is not None:
            return existing
        delivery = BriefingDelivery(
            tenant_id=tenant_id,
            briefing_date=briefing_date,
            channel="telegram",
            destination=destination,
            dedupe_key=dedupe_key,
            status=BriefingDeliveryStatus.PENDING,
            scheduled_for=scheduled_for,
        )
        session.add(delivery)
        try:
            await session.commit()
            return delivery
        except IntegrityError:
            await session.rollback()
            existing = (
                await session.scalars(
                    select(BriefingDelivery).where(BriefingDelivery.dedupe_key == dedupe_key)
                )
            ).one()
            return existing


async def _claim_delivery(
    delivery_id: str,
    *,
    current: datetime,
    destination: str,
    settings: Settings,
) -> BriefingDispatchResult | BriefingDelivery:
    async with SessionLocal() as session:
        quarantined = await session.execute(
            update(BriefingDelivery)
            .where(
                BriefingDelivery.id == delivery_id,
                BriefingDelivery.status == BriefingDeliveryStatus.SENDING,
                BriefingDelivery.lease_expires_at.is_not(None),
                BriefingDelivery.lease_expires_at <= current,
            )
            .values(
                status=BriefingDeliveryStatus.UNCERTAIN,
                lease_expires_at=None,
                next_retry_at=None,
                failure_code="delivery_outcome_unknown",
            )
        )
        if quarantined.rowcount == 1:
            delivery = await session.get(BriefingDelivery, delivery_id)
            if delivery is not None:
                add_audit_event(
                    session,
                    tenant_id=delivery.tenant_id,
                    actor="system:briefing-scheduler",
                    action="briefing.delivery.quarantined",
                    resource_type="briefing_delivery",
                    resource_id=delivery.id,
                    details={"reason": "delivery_outcome_unknown"},
                )
            await session.commit()
            return BriefingDispatchResult(
                BriefingDispatchOutcome.MANUAL_REVIEW,
                delivery_id,
                delivery.attempt_count if delivery is not None else 0,
            )
        retry_ready = or_(
            BriefingDelivery.next_retry_at.is_(None),
            BriefingDelivery.next_retry_at <= current,
        )
        claimable = and_(
            BriefingDelivery.status.in_(
                [BriefingDeliveryStatus.PENDING, BriefingDeliveryStatus.FAILED]
            ),
            retry_ready,
        )
        result = await session.execute(
            update(BriefingDelivery)
            .where(
                BriefingDelivery.id == delivery_id,
                BriefingDelivery.attempt_count < settings.briefing_max_attempts,
                claimable,
            )
            .values(
                status=BriefingDeliveryStatus.SENDING,
                destination=destination,
                attempt_count=BriefingDelivery.attempt_count + 1,
                last_attempt_at=current,
                next_retry_at=None,
                lease_expires_at=current
                + timedelta(seconds=settings.briefing_delivery_lease_seconds),
                failure_code=None,
            )
        )
        await session.commit()
        delivery = await session.get(BriefingDelivery, delivery_id)
        if delivery is None:
            return BriefingDispatchResult(BriefingDispatchOutcome.FAILED)
        if result.rowcount == 1:
            return delivery
        if delivery.status == BriefingDeliveryStatus.SENT:
            outcome = BriefingDispatchOutcome.ALREADY_SENT
        elif delivery.attempt_count >= settings.briefing_max_attempts:
            outcome = BriefingDispatchOutcome.EXHAUSTED
        elif delivery.status == BriefingDeliveryStatus.UNCERTAIN:
            outcome = BriefingDispatchOutcome.MANUAL_REVIEW
        elif delivery.status == BriefingDeliveryStatus.SENDING:
            outcome = BriefingDispatchOutcome.BUSY
        else:
            outcome = BriefingDispatchOutcome.RETRY_PENDING
        return BriefingDispatchResult(outcome, delivery.id, delivery.attempt_count)


async def _record_result(
    delivery_id: str,
    *,
    current: datetime,
    sent: bool,
    content_hash: str | None,
    failure_code: str | None,
    settings: Settings,
) -> BriefingDispatchResult:
    async with SessionLocal() as session:
        delivery = await session.get(BriefingDelivery, delivery_id)
        if delivery is None:
            return BriefingDispatchResult(BriefingDispatchOutcome.FAILED)
        if sent:
            delivery.status = BriefingDeliveryStatus.SENT
            delivery.sent_at = current
            delivery.next_retry_at = None
            delivery.failure_code = None
            action = "briefing.delivery.sent"
            outcome = BriefingDispatchOutcome.SENT
        else:
            delivery.status = BriefingDeliveryStatus.FAILED
            delivery.sent_at = None
            delivery.failure_code = (failure_code or "delivery_failed")[:120]
            delivery.next_retry_at = (
                current
                + timedelta(
                    seconds=settings.briefing_retry_seconds
                    * 2 ** max(delivery.attempt_count - 1, 0)
                )
                if delivery.attempt_count < settings.briefing_max_attempts
                else None
            )
            action = "briefing.delivery.failed"
            outcome = BriefingDispatchOutcome.FAILED
        delivery.content_hash = content_hash
        delivery.lease_expires_at = None
        add_audit_event(
            session,
            tenant_id=delivery.tenant_id,
            actor="system:briefing-scheduler",
            action=action,
            resource_type="briefing_delivery",
            resource_id=delivery.id,
            details={
                "channel": delivery.channel,
                "briefing_date": delivery.briefing_date.isoformat(),
                "attempt_count": delivery.attempt_count,
                "failure_code": delivery.failure_code,
            },
        )
        await session.commit()
        return BriefingDispatchResult(outcome, delivery.id, delivery.attempt_count)


async def dispatch_scheduled_briefing(
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    sender: DeliverySender | None = None,
) -> BriefingDispatchResult:
    """Deliver one daily Telegram briefing with durable deduplication and retries."""

    runtime_settings = settings or get_settings()
    if not runtime_settings.briefing_enabled or not runtime_settings.telegram_enabled:
        return BriefingDispatchResult(BriefingDispatchOutcome.DISABLED)
    current = as_utc(now or datetime.now(UTC))
    window = _scheduled_window(current, runtime_settings)
    if isinstance(window, BriefingDispatchOutcome):
        return BriefingDispatchResult(window)
    briefing_date, scheduled_for = window
    destination = runtime_settings.telegram_allowed_chat_id or ""
    delivery = await _get_or_create_delivery(
        tenant_id=runtime_settings.default_tenant_id,
        briefing_date=briefing_date,
        destination=destination,
        scheduled_for=scheduled_for,
    )
    claimed = await _claim_delivery(
        delivery.id,
        current=current,
        destination=destination,
        settings=runtime_settings,
    )
    if isinstance(claimed, BriefingDispatchResult):
        return claimed

    content: str | None = None
    failure_code: str | None = None
    delivered = False
    try:
        async with SessionLocal() as session:
            content = await build_daily_briefing(
                session,
                runtime_settings.default_tenant_id,
                now=current,
                settings=runtime_settings,
            )
        delivery_sender = sender or send_telegram_message
        delivered = await delivery_sender(runtime_settings, destination, content)
        if not delivered:
            failure_code = "telegram_delivery_failed"
    except Exception as exc:
        failure_code = type(exc).__name__
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest() if content else None
    return await _record_result(
        claimed.id,
        current=current,
        sent=delivered,
        content_hash=content_hash,
        failure_code=failure_code,
        settings=runtime_settings,
    )
