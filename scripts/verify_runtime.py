"""Verify configuration and infrastructure without exposing secret values."""

import argparse
import asyncio

from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db import EXPECTED_DB_REVISION, engine


async def main(config_only: bool = False) -> None:
    settings = get_settings()
    print(f"Configuration: valid ({settings.app_env}, {settings.ai_provider})")

    if config_only:
        print("Infrastructure: skipped (--config-only)")
        print(f"Telegram: {'enabled' if settings.telegram_enabled else 'disabled'}")
        print("Secrets: present values were validated but not displayed")
        return

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
        if not settings.auto_create_schema:
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != EXPECTED_DB_REVISION:
                raise RuntimeError(
                    f"Database schema revision mismatch: expected {EXPECTED_DB_REVISION}"
                )
    print("Database: reachable")
    if not settings.auto_create_schema:
        print(f"Database schema: {EXPECTED_DB_REVISION}")

    if settings.task_execution_mode == "worker":
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=5, socket_timeout=5)
        try:
            if not await redis.ping():
                raise RuntimeError("Redis PING did not return success")
        finally:
            await redis.aclose()
        print("Redis: reachable")
    else:
        print("Redis: skipped (TASK_EXECUTION_MODE is inline)")

    print(f"Telegram: {'enabled' if settings.telegram_enabled else 'disabled'}")
    print("Secrets: present values were validated but not displayed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.config_only))
