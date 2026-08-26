import pytest
from pydantic import ValidationError

from app.core.config import Settings


def production_settings(**overrides):
    values = {
        "app_env": "production",
        "database_url": "postgresql+asyncpg://app:secret@db/app",
        "task_execution_mode": "worker",
        "auto_create_schema": False,
        "ai_provider": "mock",
        "auth_enabled": True,
        "app_api_key": "a" * 32,
        "cors_origins": "https://company.example",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_baseline_is_accepted():
    settings = production_settings()

    assert settings.app_env == "production"
    assert settings.task_execution_mode == "worker"


def test_settings_repr_hides_credentials():
    settings = production_settings(
        database_url="postgresql+asyncpg://app:database-secret@db/app",
        redis_url="redis://:redis-secret@redis:6379/0",
    )

    rendered = repr(settings)
    assert "database-secret" not in rendered
    assert "redis-secret" not in rendered


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"auth_enabled": False}, "AUTH_ENABLED"),
        ({"app_api_key": "short"}, "32 characters"),
        ({"app_api_key": "replace-with-at-least-32-random-characters"}, "placeholder"),
        ({"database_url": "sqlite+aiosqlite:///./prod.db"}, "PostgreSQL"),
        (
            {"database_url": "postgresql+asyncpg://app:replace-with-secret@db/app"},
            "placeholder",
        ),
        ({"task_execution_mode": "inline"}, "worker"),
        ({"auto_create_schema": True}, "AUTO_CREATE_SCHEMA"),
        ({"cors_origins": "*"}, "Wildcard CORS"),
    ],
)
def test_unsafe_production_configuration_is_rejected(override, message):
    with pytest.raises(ValidationError, match=message):
        production_settings(**override)


def test_enabled_telegram_requires_complete_valid_https_configuration():
    with pytest.raises(ValidationError, match="TELEGRAM_BOT_TOKEN"):
        production_settings(telegram_enabled=True)

    with pytest.raises(ValidationError, match="HTTPS"):
        production_settings(
            telegram_enabled=True,
            telegram_bot_token="token",
            telegram_webhook_secret="telegram-secret-123",
            telegram_allowed_chat_id="123",
            public_base_url="http://company.example",
        )
    with pytest.raises(ValidationError, match="valid HTTPS URL"):
        production_settings(
            telegram_enabled=True,
            telegram_bot_token="token",
            telegram_webhook_secret="telegram-secret-123",
            telegram_allowed_chat_id="123",
            public_base_url="https://",
        )

    settings = production_settings(
        telegram_enabled=True,
        telegram_bot_token="token",
        telegram_webhook_secret="telegram-secret-123",
        telegram_allowed_chat_id="-123",
        public_base_url="https://company.example",
    )
    assert settings.telegram_enabled is True
