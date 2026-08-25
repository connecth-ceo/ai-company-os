from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Company OS"
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite+aiosqlite:///./ai_company.db"
    redis_url: str = "redis://localhost:6379/0"
    task_execution_mode: Literal["inline", "worker"] = "inline"
    auto_create_schema: bool = True
    ai_provider: Literal["mock", "openai"] = "mock"
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str = "gpt-5.6-luna"
    review_max_reworks: int = Field(default=1, ge=0, le=3)
    task_max_attempts: int = Field(default=3, ge=1, le=10)
    task_timeout_seconds: int = Field(default=600, ge=30, le=3600)
    auth_enabled: bool = False
    app_api_key: str | None = Field(default=None, repr=False)
    default_tenant_id: str = "owner"
    cors_origins: str = "http://localhost:8000"
    public_base_url: str = "http://localhost:8000"
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

    @model_validator(mode="after")
    def validate_openai_key(self) -> "Settings":
        if self.ai_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
        if self.auth_enabled and not self.app_api_key:
            raise ValueError("APP_API_KEY is required when AUTH_ENABLED=true")
        if self.app_env == "production" and not self.auth_enabled:
            raise ValueError("AUTH_ENABLED must be true in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
