from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends
from pydantic import StrictInt
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_se_client, get_session, get_shopify_client
from app.application.services.middleware_service import MiddlewareService
from app.core.config import settings
from app.infrastructure.db import async_session
from app.infrastructure.repositories.integration_repository import IntegrationRepository
from app.infrastructure.se.client import SEClient
from app.infrastructure.shopify.client import ShopifyClient

router = APIRouter()


def _service(session: AsyncSession, shopify_client, se_client) -> MiddlewareService:
    return MiddlewareService(
        integration_repo=IntegrationRepository(session),
        shopify_client=shopify_client,
        se_client=se_client,
    )


async def _run_product_sync_background(run_id: str, payload: Any = None) -> None:
    async with async_session() as session:
        integration_repo = IntegrationRepository(session)
        service = MiddlewareService(
            integration_repo=integration_repo,
            shopify_client=ShopifyClient(
                shop=settings.shopify_shop,
                api_version=settings.shopify_api_version,
                access_token=settings.shopify_access_token,
            ),
            se_client=SEClient(
                base_url=settings.se_base_url,
                api_key=settings.se_api_key,
                company_code=settings.se_company_code,
            ),
        )
        try:
            run = await integration_repo.get_sync_run(run_id)
            if run is None:
                return
            await service.sync_products(payload, run=run)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            async with async_session() as failure_session:
                failure_repo = IntegrationRepository(failure_session)
                run = await failure_repo.get_sync_run(run_id)
                if run is not None:
                    message = str(exc).strip() or f"{type(exc).__name__}: {exc!r}"
                    await failure_repo.finish_sync_run(run, "failed", error_message=message)
                    await failure_session.commit()


async def _run_price_sync_background(run_id: str) -> None:
    async with async_session() as session:
        integration_repo = IntegrationRepository(session)
        service = MiddlewareService(
            integration_repo=integration_repo,
            shopify_client=ShopifyClient(
                shop=settings.shopify_shop,
                api_version=settings.shopify_api_version,
                access_token=settings.shopify_access_token,
            ),
            se_client=SEClient(
                base_url=settings.se_base_url,
                api_key=settings.se_api_key,
                company_code=settings.se_company_code,
            ),
        )
        try:
            run = await integration_repo.get_sync_run(run_id)
            if run is None:
                return
            await service.sync_prices(run=run)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            async with async_session() as failure_session:
                failure_repo = IntegrationRepository(failure_session)
                run = await failure_repo.get_sync_run(run_id)
                if run is not None:
                    message = str(exc).strip() or f"{type(exc).__name__}: {exc!r}"
                    await failure_repo.finish_sync_run(run, "failed", error_message=message)
                    await failure_session.commit()


async def _run_image_sync_background(run_id: str) -> None:
    async with async_session() as session:
        integration_repo = IntegrationRepository(session)
        service = MiddlewareService(
            integration_repo=integration_repo,
            shopify_client=ShopifyClient(
                shop=settings.shopify_shop,
                api_version=settings.shopify_api_version,
                access_token=settings.shopify_access_token,
            ),
            se_client=SEClient(
                base_url=settings.se_base_url,
                api_key=settings.se_api_key,
                company_code=settings.se_company_code,
            ),
        )
        try:
            run = await integration_repo.get_sync_run(run_id)
            if run is None:
                return
            await service.sync_images(run=run)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            async with async_session() as failure_session:
                failure_repo = IntegrationRepository(failure_session)
                run = await failure_repo.get_sync_run(run_id)
                if run is not None:
                    message = str(exc).strip() or f"{type(exc).__name__}: {exc!r}"
                    await failure_repo.finish_sync_run(run, "failed", error_message=message)
                    await failure_session.commit()


async def _run_inventory_sync_background(run_id: str, payload: Any = None) -> None:
    async with async_session() as session:
        integration_repo = IntegrationRepository(session)
        service = MiddlewareService(
            integration_repo=integration_repo,
            shopify_client=ShopifyClient(
                shop=settings.shopify_shop,
                api_version=settings.shopify_api_version,
                access_token=settings.shopify_access_token,
            ),
            se_client=SEClient(
                base_url=settings.se_base_url,
                api_key=settings.se_api_key,
                company_code=settings.se_company_code,
            ),
        )
        try:
            run = await integration_repo.get_sync_run(run_id)
            if run is None:
                return
            await service.sync_inventory(payload, run=run)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            async with async_session() as failure_session:
                failure_repo = IntegrationRepository(failure_session)
                run = await failure_repo.get_sync_run(run_id)
                if run is not None:
                    message = str(exc).strip() or f"{type(exc).__name__}: {exc!r}"
                    await failure_repo.finish_sync_run(run, "failed", error_message=message)
                    await failure_session.commit()


@router.post("/products")
async def sync_products(
    background_tasks: BackgroundTasks,
    payload: StrictInt | None = Body(default=None),
    wait: bool = False,
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
    se_client=Depends(get_se_client),
) -> dict[str, Any]:
    if not wait:
        run = await IntegrationRepository(session).start_sync_run("products")
        await session.commit()
        background_tasks.add_task(_run_product_sync_background, run.id, payload)
        return {
            "status": "queued",
            "sync_type": "products",
            "run_id": run.id,
            "detail": "Product sync is running in the background. Check GET /sync/runs?sync_type=products for progress.",
        }
    return await _service(session, shopify_client, se_client).sync_products(payload)


@router.post("/prices")
async def sync_prices(
    background_tasks: BackgroundTasks,
    wait: bool = False,
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
    se_client=Depends(get_se_client),
) -> dict[str, Any]:
    if not wait:
        run = await IntegrationRepository(session).start_sync_run("prices")
        await session.commit()
        background_tasks.add_task(_run_price_sync_background, run.id)
        return {
            "status": "queued",
            "sync_type": "prices",
            "run_id": run.id,
            "detail": "Price sync is running in the background. Check GET /sync/runs?sync_type=prices for progress.",
        }
    return await _service(session, shopify_client, se_client).sync_prices()


@router.post("/inventory")
async def sync_inventory(
    background_tasks: BackgroundTasks,
    payload: StrictInt | None = Body(default=None),
    wait: bool = False,
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
    se_client=Depends(get_se_client),
) -> dict[str, Any]:
    if not wait:
        run = await IntegrationRepository(session).start_sync_run("inventory")
        await session.commit()
        background_tasks.add_task(_run_inventory_sync_background, run.id, payload)
        return {
            "status": "queued",
            "sync_type": "inventory",
            "run_id": run.id,
            "detail": "Inventory sync is running in the background. Check GET /sync/runs?sync_type=inventory for progress.",
        }
    return await _service(session, shopify_client, se_client).sync_inventory(payload)


@router.post("/images")
async def sync_images(
    background_tasks: BackgroundTasks,
    wait: bool = False,
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
    se_client=Depends(get_se_client),
) -> dict[str, Any]:
    if not wait:
        run = await IntegrationRepository(session).start_sync_run("images")
        await session.commit()
        background_tasks.add_task(_run_image_sync_background, run.id)
        return {
            "status": "queued",
            "sync_type": "images",
            "run_id": run.id,
            "detail": "Image sync is running in the background. Check GET /sync/runs?sync_type=images for progress.",
        }
    return await _service(session, shopify_client, se_client).sync_images()


@router.post("/branches")
async def sync_branches(
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
    se_client=Depends(get_se_client),
) -> dict[str, Any]:
    return await _service(session, shopify_client, se_client).sync_branches()


@router.post("/customers")
async def sync_customers(
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
    se_client=Depends(get_se_client),
) -> dict[str, Any]:
    return await _service(session, shopify_client, se_client).sync_customers()


@router.post("/invoices")
async def send_invoice(
    payload: list[dict[str, Any]] | dict[str, Any] = Body(...),
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
    se_client=Depends(get_se_client),
) -> dict[str, Any]:
    return await _service(session, shopify_client, se_client).send_invoice(payload)


# @router.post("/invoice-visits")
# async def send_invoice_visit(
#     payload: list[dict[str, Any]] | dict[str, Any] = Body(...),
#     session: AsyncSession = Depends(get_session),
#     shopify_client=Depends(get_shopify_client),
#     se_client=Depends(get_se_client),
# ) -> dict[str, Any]:
#     return await _service(session, shopify_client, se_client).send_invoice_visit(payload)


@router.post("/taxonomy")
async def sync_taxonomy(
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
    se_client=Depends(get_se_client),
) -> dict[str, Any]:
    return await _service(session, shopify_client, se_client).sync_catalog_taxonomy()


@router.get("/runs")
async def sync_runs(
    sync_type: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    runs = await IntegrationRepository(session).list_sync_runs(sync_type=sync_type)
    return [
        {
            "id": run.id,
            "sync_type": run.sync_type,
            "status": run.status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "stats": run.stats,
            "error_message": run.error_message,
        }
        for run in runs
    ]
