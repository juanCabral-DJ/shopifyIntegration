from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.application.services.middleware_service import MiddlewareService
from app.core.config import settings
from app.infrastructure.db import async_session
from app.infrastructure.repositories.integration_repository import IntegrationRepository
from app.infrastructure.se.client import SEClient
from app.infrastructure.shopify.client import ShopifyClient


async def on_startup(ctx: dict[str, Any]) -> None:
    ctx["sessionmaker"] = async_session
    ctx["se_client"] = SEClient(
        base_url=settings.se_base_url,
        api_key=settings.se_api_key,
        company_code=settings.se_company_code,
    )
    ctx["shopify_client"] = ShopifyClient(
        shop=settings.shopify_shop,
        api_version=settings.shopify_api_version,
        access_token=settings.shopify_access_token,
    )


async def on_shutdown(ctx: dict[str, Any]) -> None:
    ctx.clear()


def _service(ctx: dict[str, Any], session) -> MiddlewareService:
    return MiddlewareService(
        integration_repo=IntegrationRepository(session),
        shopify_client=ctx["shopify_client"],
        se_client=ctx["se_client"],
    )


async def process_pending_outbox(ctx: dict[str, Any]) -> dict[str, Any]:
    async with ctx["sessionmaker"]() as session:
        result = await _service(ctx, session).process_pending_outbox(limit=settings.outbox_batch_size)
        await session.commit()
        return result


async def price_sync(ctx: dict[str, Any]) -> dict[str, Any]:
    async with ctx["sessionmaker"]() as session:
        result = await _service(ctx, session).sync_prices()
        await session.commit()
        return result


async def inventory_sync(ctx: dict[str, Any]) -> dict[str, Any]:
    async with ctx["sessionmaker"]() as session:
        result = await _service(ctx, session).sync_inventory()
        await session.commit()
        return result


async def payment_polling(ctx: dict[str, Any]) -> dict[str, Any]:
    async with ctx["sessionmaker"]() as session:
        result = await _service(ctx, session).payment_polling()
        await session.commit()
        return result


async def inventory_reconcile(ctx: dict[str, Any]) -> dict[str, Any]:
    async with ctx["sessionmaker"]() as session:
        result = await _service(ctx, session).sync_inventory(reconcile=True)
        await session.commit()
        return result


class WorkerSettings:
    functions = [process_pending_outbox]
    cron_jobs = [
        cron(process_pending_outbox, second=set(range(0, 60, 5))),
        cron(price_sync, minute=set(range(0, 60, 2))),
        cron(inventory_sync, minute=set(range(0, 60, 5))),
        cron(payment_polling, minute=set(range(0, 60, 3))),
        cron(inventory_reconcile, minute={0, 30}),
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url) if settings.redis_url else RedisSettings()
