import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.api.routers.auth import router as auth_router
from app.api.routers.events import router as events_router
from app.api.routers.mappings import router as mappings_router
from app.api.routers.retry import router as retry_router
from app.api.routers.sync import router as sync_router
from app.api.routers.webhooks import router as webhooks_router
from app.core.config import settings
from app.infrastructure.db import async_session

app = FastAPI(
    title="shopifyPayments",
    version="1.0.0",
    debug=settings.debug_errors,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(sync_router, prefix="/sync", tags=["sync"])
app.include_router(mappings_router, prefix="/mappings", tags=["mappings"])
app.include_router(events_router, prefix="/events", tags=["events"])
app.include_router(retry_router, tags=["retry"])


@app.get("/", tags=["health"], response_model=None)
async def root():
    return {
        "status": "ok",
        "service": "shopifyPayments",
        "health": "/health",
        "ready": "/ready",
    }


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "shopifyPayments"}


@app.get("/ready", tags=["health"])
async def ready() -> dict[str, object]:
    checks: dict[str, object] = {
        "database": "unknown",
        "redis": "not_configured",
        "external_system": "configured" if settings.se_base_url else "not_configured",
    }
    async with async_session() as session:
        await session.execute(text("select 1"))
        checks["database"] = "ok"
    if settings.redis_url:
        checks["redis"] = "configured"
    return {"status": "ok", "checks": checks}
