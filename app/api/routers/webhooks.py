from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, get_shopify_client
from app.api.schemas.webhook import WebhookLogResponse
from app.application.services.webhook_service import WebhookService
from app.core.config import settings
from app.core.security import verify_shopify_webhook
from app.infrastructure.repositories.customer_repository import CustomerRepository
from app.infrastructure.repositories.integration_repository import IntegrationRepository
from app.infrastructure.repositories.inventory_repository import InventoryRepository
from app.infrastructure.repositories.order_repository import OrderRepository
from app.infrastructure.repositories.payment_method_repository import PaymentMethodRepository
from app.infrastructure.repositories.webhook_repository import WebhookRepository

router = APIRouter()


async def _verified_payload(request: Request, hmac_header: str | None) -> dict:
    raw_body = await request.body()
    if not hmac_header or not verify_shopify_webhook(settings.shopify_webhook_secret, raw_body, hmac_header):
        raise HTTPException(status_code=401, detail="Invalid Shopify HMAC signature")
    return await request.json()


def _webhook_service(session: AsyncSession, shopify_client, inventory: bool = False) -> WebhookService:
    return WebhookService(
        webhook_repo=WebhookRepository(session),
        order_repo=OrderRepository(session),
        customer_repo=CustomerRepository(session),
        payment_method_repo=PaymentMethodRepository(session),
        inventory_repo=InventoryRepository(session) if inventory else None,
        shopify_client=shopify_client,
        integration_repo=IntegrationRepository(session),
    )


async def _handle_order_webhook(
    request: Request,
    topic: str,
    hmac_header: str | None,
    delivery_attempts: str | None,
    session: AsyncSession,
    shopify_client,
) -> dict[str, str]:
    payload = await _verified_payload(request, hmac_header)
    service = _webhook_service(session, shopify_client)
    await service.handle_order_event(payload, topic, int(delivery_attempts or 1))
    return {"status": "accepted"}


async def _handle_inventory_webhook(
    request: Request,
    topic: str,
    hmac_header: str | None,
    delivery_attempts: str | None,
    session: AsyncSession,
    shopify_client,
) -> dict[str, str]:
    payload = await _verified_payload(request, hmac_header)
    service = _webhook_service(session, shopify_client, inventory=True)
    await service.handle_inventory_event(payload, topic, int(delivery_attempts or 1))
    return {"status": "accepted"}


@router.post("/orders/create")
async def shopify_orders_create_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_delivery_attempts: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
) -> dict[str, str]:
    return await _handle_order_webhook(
        request=request,
        topic="orders/create",
        hmac_header=x_shopify_hmac_sha256,
        delivery_attempts=x_shopify_delivery_attempts,
        session=session,
        shopify_client=shopify_client,
    )


@router.post("/orders/updated")
async def shopify_orders_updated_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_delivery_attempts: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
) -> dict[str, str]:
    return await _handle_order_webhook(
        request=request,
        topic="orders/updated",
        hmac_header=x_shopify_hmac_sha256,
        delivery_attempts=x_shopify_delivery_attempts,
        session=session,
        shopify_client=shopify_client,
    )


@router.post("/orders/paid")
async def shopify_orders_paid_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_delivery_attempts: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
) -> dict[str, str]:
    return await _handle_order_webhook(
        request=request,
        topic="orders/paid",
        hmac_header=x_shopify_hmac_sha256,
        delivery_attempts=x_shopify_delivery_attempts,
        session=session,
        shopify_client=shopify_client,
    )


@router.post("/orders/cancelled")
async def shopify_orders_cancelled_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_delivery_attempts: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
) -> dict[str, str]:
    return await _handle_order_webhook(
        request=request,
        topic="orders/cancelled",
        hmac_header=x_shopify_hmac_sha256,
        delivery_attempts=x_shopify_delivery_attempts,
        session=session,
        shopify_client=shopify_client,
    )


@router.post("/refunds/create")
async def shopify_refunds_create_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_delivery_attempts: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
) -> dict[str, str]:
    return await _handle_inventory_webhook(
        request=request,
        topic="refunds/create",
        hmac_header=x_shopify_hmac_sha256,
        delivery_attempts=x_shopify_delivery_attempts,
        session=session,
        shopify_client=shopify_client,
    )


@router.post("/fulfillments/create")
async def shopify_fulfillments_create_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_delivery_attempts: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
) -> dict[str, str]:
    return await _handle_inventory_webhook(
        request=request,
        topic="fulfillments/create",
        hmac_header=x_shopify_hmac_sha256,
        delivery_attempts=x_shopify_delivery_attempts,
        session=session,
        shopify_client=shopify_client,
    )


@router.post("/customers/create")
async def shopify_customers_create_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_delivery_attempts: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
) -> dict[str, str]:
    return await _handle_inventory_webhook(
        request=request,
        topic="customers/create",
        hmac_header=x_shopify_hmac_sha256,
        delivery_attempts=x_shopify_delivery_attempts,
        session=session,
        shopify_client=shopify_client,
    )


@router.post("/customers/update")
async def shopify_customers_update_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_delivery_attempts: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
) -> dict[str, str]:
    return await _handle_inventory_webhook(
        request=request,
        topic="customers/update",
        hmac_header=x_shopify_hmac_sha256,
        delivery_attempts=x_shopify_delivery_attempts,
        session=session,
        shopify_client=shopify_client,
    )


@router.post("/inventory-levels/update")
async def shopify_inventory_levels_update_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_delivery_attempts: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
) -> dict[str, str]:
    return await _handle_inventory_webhook(
        request=request,
        topic="inventory_levels/update",
        hmac_header=x_shopify_hmac_sha256,
        delivery_attempts=x_shopify_delivery_attempts,
        session=session,
        shopify_client=shopify_client,
    )


@router.post("/inventory-items/update")
async def shopify_inventory_items_update_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_delivery_attempts: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
) -> dict[str, str]:
    return await _handle_inventory_webhook(
        request=request,
        topic="inventory_items/update",
        hmac_header=x_shopify_hmac_sha256,
        delivery_attempts=x_shopify_delivery_attempts,
        session=session,
        shopify_client=shopify_client,
    )


@router.post("/products/update")
async def shopify_products_update_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_delivery_attempts: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
    shopify_client=Depends(get_shopify_client),
) -> dict[str, str]:
    return await _handle_inventory_webhook(
        request=request,
        topic="products/update",
        hmac_header=x_shopify_hmac_sha256,
        delivery_attempts=x_shopify_delivery_attempts,
        session=session,
        shopify_client=shopify_client,
    )


@router.get("/logs", response_model=list[WebhookLogResponse])
async def webhook_logs(session: AsyncSession = Depends(get_session)) -> list[WebhookLogResponse]:
    repo = WebhookRepository(session)
    events = await repo.list_events()
    return [WebhookLogResponse.model_validate(event) for event in events]
