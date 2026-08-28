import re
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Company OS"
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = Field(default="sqlite+aiosqlite:///./ai_company.db", repr=False)
    redis_url: str = Field(default="redis://localhost:6379/0", repr=False)
    task_execution_mode: Literal["inline", "worker"] = "inline"
    auto_create_schema: bool = True
    ai_provider: Literal["mock", "openai"] = "mock"
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str = "gpt-5.6-luna"
    openai_tracing_enabled: bool = False
    openai_store_responses: bool = False
    review_max_reworks: int = Field(default=1, ge=0, le=3)
    task_max_attempts: int = Field(default=3, ge=1, le=10)
    task_timeout_seconds: int = Field(default=600, ge=30, le=3600)
    delegation_max_depth: int = Field(default=3, ge=1, le=10)
    delegation_max_children: int = Field(default=5, ge=1, le=50)
    delegation_max_token_budget: int = Field(default=50_000, ge=1, le=1_000_000)
    delegation_max_timeout_seconds: int = Field(default=900, ge=30, le=3600)
    delegation_max_cost_usd: float = Field(default=5.0, gt=0, le=1_000)
    delegation_approval_cost_threshold_usd: float = Field(default=1.0, gt=0, le=1_000)
    delegation_approval_roles: str = "legal_review"
    auth_enabled: bool = False
    app_api_key: str | None = Field(default=None, repr=False)
    default_tenant_id: str = "owner"
    cors_origins: str = "http://localhost:8000"
    public_base_url: str = "http://localhost:8000"
    telegram_enabled: bool = False
    telegram_bot_token: str | None = Field(default=None, repr=False)
    telegram_webhook_secret: str | None = Field(default=None, repr=False)
    telegram_allowed_chat_id: str | None = None

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://") and "+asyncpg" not in value:
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def delegation_approval_role_set(self) -> set[str]:
        return {role.strip() for role in self.delegation_approval_roles.split(",") if role.strip()}

    @model_validator(mode="after")
    def validate_runtime_configuration(self) -> "Settings":
        if self.delegation_approval_cost_threshold_usd > self.delegation_max_cost_usd:
            raise ValueError(
                "DELEGATION_APPROVAL_COST_THRESHOLD_USD cannot exceed DELEGATION_MAX_COST_USD"
            )
        if any(
            not re.fullmatch(r"[a-z][a-z0-9_]*", role) for role in self.delegation_approval_role_set
        ):
            raise ValueError("DELEGATION_APPROVAL_ROLES must be comma-separated agent role keys")
        if self.ai_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
        if self.auth_enabled and not self.app_api_key:
            raise ValueError("APP_API_KEY is required when AUTH_ENABLED=true")
        telegram_values = (
            self.telegram_bot_token,
            self.telegram_webhook_secret,
            self.telegram_allowed_chat_id,
        )
        if self.telegram_enabled and not all(telegram_values):
            raise ValueError(
                "TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, and "
                "TELEGRAM_ALLOWED_CHAT_ID are required when TELEGRAM_ENABLED=true"
            )
        if self.telegram_enabled:
            secret = self.telegram_webhook_secret or ""
            if not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", secret):
                raise ValueError(
                    "TELEGRAM_WEBHOOK_SECRET must be 16-256 characters using letters, "
                    "numbers, underscore, or hyphen"
                )
            if not re.fullmatch(r"-?[0-9]+", self.telegram_allowed_chat_id or ""):
                raise ValueError("TELEGRAM_ALLOWED_CHAT_ID must be a numeric chat ID")
        if self.app_env == "production":
            if not self.auth_enabled:
                raise ValueError("AUTH_ENABLED must be true in production")
            if len(self.app_api_key or "") < 32:
                raise ValueError("APP_API_KEY must contain at least 32 characters in production")
            if "replace-with" in (self.app_api_key or "").lower():
                raise ValueError("APP_API_KEY placeholder must be replaced in production")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Production requires PostgreSQL; SQLite is not supported")
            if "replace-with" in self.database_url.lower():
                raise ValueError("DATABASE_URL placeholder must be replaced in production")
            if self.task_execution_mode != "worker":
                raise ValueError("TASK_EXECUTION_MODE must be worker in production")
            if self.auto_create_schema:
                raise ValueError("AUTO_CREATE_SCHEMA must be false in production")
            if "*" in self.cors_origin_list:
                raise ValueError("Wildcard CORS origins are not allowed in production")
            if self.telegram_enabled:
                public_url = urlparse(self.public_base_url)
                if public_url.scheme != "https" or not public_url.netloc:
                    raise ValueError(
                        "PUBLIC_BASE_URL must be a valid HTTPS URL when Telegram is enabled"
                    )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
