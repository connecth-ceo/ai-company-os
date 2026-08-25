from unittest.mock import AsyncMock, patch

from app.core.config import Settings, get_settings
from app.main import app


def test_dashboard_and_readiness(client):
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "AI Company OS" in dashboard.text

    readiness = client.get("/ready")
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ready"


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
        telegram_bot_token="test-token",
        telegram_webhook_secret="webhook-secret",
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
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["method"] == "sendMessage"


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
        telegram_bot_token="test-token",
        telegram_webhook_secret="webhook-secret",
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
                headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
            )
            tasks = client.get("/api/v1/tasks").json()
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200
    assert tasks[0]["source"] == "telegram"
    assert tasks[0]["status"] == "completed"
    send_mock.assert_awaited_once()
