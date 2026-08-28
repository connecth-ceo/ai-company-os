from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.config import Settings
from app.db import SessionLocal
from app.models import AuditEvent, BriefingDelivery, BriefingDeliveryStatus
from app.services.briefing_delivery import (
    BriefingDispatchOutcome,
    dispatch_scheduled_briefing,
)
from app.services.daily_briefing import MAX_BRIEFING_CHARS, limit_briefing_text


def briefing_settings(**overrides) -> Settings:
    values = {
        "ai_provider": "mock",
        "telegram_enabled": True,
        "telegram_bot_token": "test-token",
        "telegram_webhook_secret": "test-webhook-secret",
        "telegram_allowed_chat_id": "123",
        "briefing_enabled": True,
        "briefing_retry_seconds": 300,
    }
    values.update(overrides)
    return Settings(**values)


async def delivery_rows() -> list[BriefingDelivery]:
    async with SessionLocal() as session:
        return list(await session.scalars(select(BriefingDelivery)))


def test_briefing_text_is_kept_to_one_safe_telegram_message():
    text = limit_briefing_text("제목\n" + "가" * 8_000)

    assert len(text) <= MAX_BRIEFING_CHARS
    assert text.endswith("전체 내용은 CEO Desk에서 확인해 주세요.")


async def test_disabled_and_quiet_hours_do_not_create_delivery():
    disabled = await dispatch_scheduled_briefing(settings=Settings(ai_provider="mock"))
    quiet = await dispatch_scheduled_briefing(
        settings=briefing_settings(),
        now=datetime(2026, 8, 27, 21, 30, tzinfo=UTC),  # 06:30 KST
    )

    assert disabled.outcome == BriefingDispatchOutcome.DISABLED
    assert quiet.outcome == BriefingDispatchOutcome.QUIET_HOURS
    assert await delivery_rows() == []


async def test_daily_delivery_is_sent_once_and_deduplicated():
    sender = AsyncMock(return_value=True)
    current = datetime(2026, 8, 27, 22, 5, tzinfo=UTC)  # 07:05 KST

    first = await dispatch_scheduled_briefing(
        settings=briefing_settings(), now=current, sender=sender
    )
    duplicate = await dispatch_scheduled_briefing(
        settings=briefing_settings(), now=current + timedelta(minutes=5), sender=sender
    )

    rows = await delivery_rows()
    assert first.outcome == BriefingDispatchOutcome.SENT
    assert duplicate.outcome == BriefingDispatchOutcome.ALREADY_SENT
    assert sender.await_count == 1
    assert len(rows) == 1
    assert rows[0].briefing_date == date(2026, 8, 28)
    assert rows[0].status == BriefingDeliveryStatus.SENT
    assert rows[0].attempt_count == 1
    assert rows[0].content_hash is not None and len(rows[0].content_hash) == 64

    async with SessionLocal() as session:
        events = list(
            await session.scalars(
                select(AuditEvent).where(AuditEvent.action == "briefing.delivery.sent")
            )
        )
    assert len(events) == 1
    assert "destination" not in events[0].details


async def test_failed_delivery_waits_then_retries_safely():
    sender = AsyncMock(side_effect=[False, True])
    settings = briefing_settings()
    current = datetime(2026, 8, 27, 22, 5, tzinfo=UTC)

    failed = await dispatch_scheduled_briefing(settings=settings, now=current, sender=sender)
    too_soon = await dispatch_scheduled_briefing(
        settings=settings, now=current + timedelta(minutes=2), sender=sender
    )
    retried = await dispatch_scheduled_briefing(
        settings=settings, now=current + timedelta(minutes=6), sender=sender
    )

    row = (await delivery_rows())[0]
    assert failed.outcome == BriefingDispatchOutcome.FAILED
    assert too_soon.outcome == BriefingDispatchOutcome.RETRY_PENDING
    assert retried.outcome == BriefingDispatchOutcome.SENT
    assert sender.await_count == 2
    assert row.status == BriefingDeliveryStatus.SENT
    assert row.attempt_count == 2
    assert row.failure_code is None
    assert row.next_retry_at is None


async def test_delivery_stops_after_configured_attempt_limit():
    sender = AsyncMock(return_value=False)
    settings = briefing_settings(briefing_max_attempts=2)
    current = datetime(2026, 8, 27, 22, 5, tzinfo=UTC)

    await dispatch_scheduled_briefing(settings=settings, now=current, sender=sender)
    second = await dispatch_scheduled_briefing(
        settings=settings, now=current + timedelta(minutes=6), sender=sender
    )
    exhausted = await dispatch_scheduled_briefing(
        settings=settings, now=current + timedelta(minutes=20), sender=sender
    )

    row = (await delivery_rows())[0]
    assert second.outcome == BriefingDispatchOutcome.FAILED
    assert exhausted.outcome == BriefingDispatchOutcome.EXHAUSTED
    assert sender.await_count == 2
    assert row.attempt_count == 2
    assert row.next_retry_at is None


async def test_expired_sending_lease_is_quarantined_without_duplicate_send():
    current = datetime(2026, 8, 27, 22, 5, tzinfo=UTC)
    async with SessionLocal() as session:
        delivery = BriefingDelivery(
            tenant_id="owner",
            briefing_date=date(2026, 8, 28),
            channel="telegram",
            destination="123",
            dedupe_key="daily-briefing:owner:2026-08-28:telegram",
            status=BriefingDeliveryStatus.SENDING,
            scheduled_for=datetime(2026, 8, 27, 22, 0, tzinfo=UTC),
            attempt_count=1,
            last_attempt_at=current - timedelta(minutes=20),
            lease_expires_at=current - timedelta(minutes=10),
        )
        session.add(delivery)
        await session.commit()

    sender = AsyncMock(return_value=True)
    result = await dispatch_scheduled_briefing(
        settings=briefing_settings(),
        now=current,
        sender=sender,
    )

    row = (await delivery_rows())[0]
    assert result.outcome == BriefingDispatchOutcome.MANUAL_REVIEW
    assert row.status == BriefingDeliveryStatus.UNCERTAIN
    assert row.attempt_count == 1
    assert row.failure_code == "delivery_outcome_unknown"
    sender.assert_not_awaited()


async def test_delivery_history_api_is_tenant_isolated(client):
    async with SessionLocal() as session:
        session.add_all(
            [
                BriefingDelivery(
                    tenant_id=tenant,
                    briefing_date=date(2026, 8, 28),
                    channel="telegram",
                    destination="hidden",
                    dedupe_key=f"daily-briefing:{tenant}:2026-08-28:telegram",
                    status=BriefingDeliveryStatus.PENDING,
                    scheduled_for=datetime(2026, 8, 27, 22, 0, tzinfo=UTC),
                )
                for tenant in ("owner", "other")
            ]
        )
        await session.commit()

    response = client.get("/api/v1/briefing-deliveries")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["tenant_id"] == "owner"
    assert "destination" not in response.json()[0]

    schedule = client.get("/api/v1/briefing-schedule")
    assert schedule.status_code == 200
    assert schedule.json()["daily_time"] == "07:00"
    assert schedule.json()["quiet_hours"] == "22:00-07:00"
    assert schedule.json()["last_delivery"]["tenant_id"] == "owner"
