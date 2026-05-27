from typing import Any

from app.application.services.middleware_service import MiddlewareService


async def insert_invoice_job(service: MiddlewareService, order_payload: dict[str, Any]) -> None:
    await service.register_shopify_event("orders/create", order_payload)


async def product_sync_job(service: MiddlewareService) -> dict[str, Any]:
    return await service.sync_products()


async def price_sync_job(service: MiddlewareService) -> dict[str, Any]:
    return await service.sync_prices()


async def inventory_sync_job(service: MiddlewareService) -> dict[str, Any]:
    return await service.sync_inventory()


async def inventory_reconcile_job(service: MiddlewareService) -> dict[str, Any]:
    return await service.sync_inventory(reconcile=True)


async def image_sync_job(service: MiddlewareService, payload: dict[str, Any]) -> dict[str, Any]:
    return await service.sync_images(payload)


async def customer_sync_job(service: MiddlewareService) -> dict[str, Any]:
    return await service.sync_customers()


async def branch_sync_job(service: MiddlewareService) -> dict[str, Any]:
    return await service.sync_branches()


async def taxonomy_sync_job(service: MiddlewareService) -> dict[str, Any]:
    return await service.sync_catalog_taxonomy()
