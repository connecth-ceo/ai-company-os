import importlib

import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.db import EXPECTED_DB_REVISION, engine


@pytest.mark.asyncio
async def test_migration_managed_readiness_requires_expected_revision(monkeypatch):
    main_module = importlib.import_module("app.main")
    managed_settings = Settings(
        app_env="test",
        ai_provider="mock",
        auto_create_schema=False,
        task_execution_mode="inline",
    )
    monkeypatch.setattr(main_module, "settings", managed_settings)

    async with engine.begin() as connection:
        await connection.execute(
            text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        await connection.execute(text("DELETE FROM alembic_version"))
        await connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('wrong-revision')")
        )

    with pytest.raises(RuntimeError, match="schema revision mismatch"):
        await main_module.ready()

    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM alembic_version"))
        await connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": EXPECTED_DB_REVISION},
        )

    result = await main_module.ready()
    assert result["components"]["schema"] == EXPECTED_DB_REVISION
