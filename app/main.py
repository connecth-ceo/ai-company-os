from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.routes import router
from app.api.telegram import router as telegram_router
from app.core.config import get_settings
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.db import EXPECTED_DB_REVISION, engine, init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    if get_settings().auto_create_schema:
        await init_db()
    yield


settings = get_settings()
configure_logging()
app = FastAPI(title=settings.app_name, version="0.4.0", lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-API-Key", "X-Tenant-ID", "Content-Type", "X-Request-ID"],
)
app.include_router(router)
app.include_router(telegram_router)
web_dir = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=web_dir), name="static")


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(web_dir / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/ready")
async def ready() -> dict[str, str | dict[str, str]]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
        if not settings.auto_create_schema:
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != EXPECTED_DB_REVISION:
                raise RuntimeError(
                    f"Database schema revision mismatch: expected {EXPECTED_DB_REVISION}"
                )
    components = {"database": "ready"}
    if not settings.auto_create_schema:
        components["schema"] = EXPECTED_DB_REVISION
    if settings.task_execution_mode == "worker":
        from redis.asyncio import Redis

        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
        try:
            await redis.ping()
            components["redis"] = "ready"
        finally:
            await redis.aclose()
    return {"status": "ready", "components": components}
