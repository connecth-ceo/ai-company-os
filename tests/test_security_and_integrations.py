import logging
from unittest.mock import AsyncMock, patch

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.main import app


def test_dashboard_and_readiness(client):
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "AI Company OS" in dashboard.text
    assert 'id="decision-lifecycle-status"' in dashboard.text
    assert 'id="decision-supersedes"' in dashboard.text
    assert dashboard.headers["X-Content-Type-Options"] == "nosniff"
    assert dashboard.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in dashboard.headers["Content-Security-Policy"]

    readiness = client.get("/ready")
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ready"


def test_http_client_info_logging_is_suppressed():
    configure_logging()

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_idempotency_tenant_isolation_and_audit(client):
    payload = {
        "title": "중복 방지 업무",
        "request": "같은 업무는 한 번만 생성한다.",
        "idempotency_key": "same-request-001",
    }
    owner_headers = {"X-Tenant-ID": "owner"}
    other_headers = {"X-Tenant-ID": "other"}

    first = client.post("/api/v1/tasks", json=payload, headers=owner_headers)
    duplicate = client.post("/api/v1/tasks", json=payload, headers=owner_headers)
    other = client.post("/api/v1/tasks", json=payload, headers=other_headers)

    assert first.json()["id"] == duplicate.json()["id"]
    assert other.json()["id"] != first.json()["id"]
    assert len(client.get("/api/v1/tasks", headers=owner_headers).json()) == 1
    assert len(client.get("/api/v1/tasks", headers=other_headers).json()) == 1

    events = client.get("/api/v1/audit-events", headers=owner_headers).json()
    assert any(event["action"] == "task.created" for event in events)


def test_telegram_webhook_secret_and_help(client):
    telegram_settings = Settings(
        ai_provider="mock",
        auth_enabled=False,
        telegram_enabled=True,
        telegram_bot_token="test-token",
        telegram_webhook_secret="webhook-secret-123",
        telegram_allowed_chat_id="123",
    )
    app.dependency_overrides[get_settings] = lambda: telegram_settings
    update = {
        "update_id": 10,
        "message": {"chat": {"id": 123}, "text": "/start"},
    }
    try:
        rejected = client.post("/integrations/telegram/webhook", json=update)
        accepted = client.post(
            "/integrations/telegram/webhook",
            json=update,
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret-123"},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["method"] == "sendMessage"


def test_telegram_briefing_and_specialist_commands(client):
    telegram_settings = Settings(
        ai_provider="mock",
        auth_enabled=False,
        task_execution_mode="inline",
        telegram_enabled=True,
        telegram_bot_token="test-token",
        telegram_webhook_secret="webhook-secret-123",
        telegram_allowed_chat_id="123",
    )
    app.dependency_overrides[get_settings] = lambda: telegram_settings
    headers = {"X-Telegram-Bot-Api-Secret-Token": "webhook-secret-123"}
    try:
        briefing = client.post(
            "/integrations/telegram/webhook",
            json={"update_id": 20, "message": {"chat": {"id": 123}, "text": "/briefing"}},
            headers=headers,
        )
        missing_request = client.post(
            "/integrations/telegram/webhook",
            json={"update_id": 21, "message": {"chat": {"id": 123}, "text": "/marketing"}},
            headers=headers,
        )
        with patch(
            "app.services.telegram.send_telegram_message",
            new=AsyncMock(return_value=True),
        ):
            marketing = client.post(
                "/integrations/telegram/webhook",
                json={
                    "update_id": 22,
                    "message": {"chat": {"id": 123}, "text": "/marketing 제품 소개문"},
                },
                headers=headers,
            )
            task = client.get("/api/v1/tasks").json()[0]
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert briefing.status_code == 200
    assert "데일리 브리핑" in briefing.json()["text"]
    assert "명령 뒤에" in missing_request.json()["text"]
    assert marketing.status_code == 200
    assert task["status"] == "completed"
    assert task["request"].startswith("/marketing")


def test_api_key_authentication(client):
    protected_settings = Settings(ai_provider="mock", auth_enabled=True, app_api_key="secret")
    app.dependency_overrides[get_settings] = lambda: protected_settings
    try:
        rejected = client.get("/api/v1/tasks")
        accepted = client.get("/api/v1/tasks", headers={"X-API-Key": "secret"})
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert rejected.status_code == 401
    assert accepted.status_code == 200


def test_telegram_message_creates_and_completes_task(client):
    telegram_settings = Settings(
        ai_provider="mock",
        auth_enabled=False,
        task_execution_mode="inline",
        telegram_enabled=True,
        telegram_bot_token="test-token",
        telegram_webhook_secret="webhook-secret-123",
        telegram_allowed_chat_id="123",
    )
    app.dependency_overrides[get_settings] = lambda: telegram_settings
    update = {
        "update_id": 11,
        "message": {"chat": {"id": 123}, "text": "다음 분기 실행 계획을 만들어줘."},
    }
    try:
        with patch(
            "app.services.telegram.send_telegram_message",
            new=AsyncMock(return_value=True),
        ) as send_mock:
            response = client.post(
                "/integrations/telegram/webhook",
                json=update,
                headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret-123"},
            )
            tasks = client.get("/api/v1/tasks").json()
            events = client.get("/api/v1/audit-events").json()
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200
    assert tasks[0]["source"] == "telegram"
    assert tasks[0]["status"] == "completed"
    send_mock.assert_awaited_once()
    assert any(event["action"] == "task.dispatched" for event in events)
    assert any(event["action"] == "telegram.notification.sent" for event in events)


def test_telegram_rejects_missing_update_id(client):
    telegram_settings = Settings(
        ai_provider="mock",
        auth_enabled=False,
        telegram_enabled=True,
        telegram_bot_token="test-token",
        telegram_webhook_secret="webhook-secret-123",
        telegram_allowed_chat_id="123",
    )
    app.dependency_overrides[get_settings] = lambda: telegram_settings
    try:
        response = client.post(
            "/integrations/telegram/webhook",
            json={"message": {"chat": {"id": 123}, "text": "업무 요청"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret-123"},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 400
    assert response.json()["detail"] == "Telegram update_id is required"


def test_telegram_queue_failure_can_be_retried_with_same_update(client):
    telegram_settings = Settings(
        ai_provider="mock",
        auth_enabled=False,
        task_execution_mode="worker",
        telegram_enabled=True,
        telegram_bot_token="test-token",
        telegram_webhook_secret="webhook-secret-123",
        telegram_allowed_chat_id="123",
    )
    app.dependency_overrides[get_settings] = lambda: telegram_settings
    update = {
        "update_id": 12,
        "message": {"chat": {"id": 123}, "text": "큐 재시도 확인"},
    }
    headers = {"X-Telegram-Bot-Api-Secret-Token": "webhook-secret-123"}
    try:
        with patch("app.worker.execute_task_job.delay", side_effect=ConnectionError):
            failed = client.post("/integrations/telegram/webhook", json=update, headers=headers)
        queued = client.get("/api/v1/tasks").json()[0]
        with patch("app.worker.execute_task_job.delay") as delay_mock:
            retried = client.post("/integrations/telegram/webhook", json=update, headers=headers)
            duplicate = client.post("/integrations/telegram/webhook", json=update, headers=headers)
        dispatched = client.get("/api/v1/tasks").json()[0]
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert failed.status_code == 503
    assert queued["status"] == "queued"
    assert retried.status_code == 200
    assert duplicate.status_code == 200
    assert dispatched["status"] == "dispatched"
    delay_mock.assert_called_once_with(dispatched["id"])
