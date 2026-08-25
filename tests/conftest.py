import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_ai_company.db"
os.environ["TASK_EXECUTION_MODE"] = "inline"
os.environ["AI_PROVIDER"] = "mock"

import pytest_asyncio
from fastapi.testclient import TestClient

from app.db import engine
from app.main import app
from app.models import Base


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def client():
    with TestClient(app) as test_client:
        yield test_client
