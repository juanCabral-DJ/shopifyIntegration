from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.application.services.middleware_service import MiddlewareService
from app.infrastructure.repositories.integration_repository import IntegrationRepository

router = APIRouter()


@router.post("/orders/{shopify_order_id}/retry")
async def retry_order_invoice(
    shopify_order_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    service = MiddlewareService(integration_repo=IntegrationRepository(session))
    return await service.retry_order_invoice(shopify_order_id)

#atender aqui que se llama a getFactura
@router.post("/payments/{shopify_order_id}/retry")  
async def retry_order_payment(
    shopify_order_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    service = MiddlewareService(integration_repo=IntegrationRepository(session))
    return await service.retry_outbox_event(shopify_order_id, {"payment.poll", "payments.sync", "Factura.GetFacturas"})


@router.post("/invoices/{shopify_order_id}/retry")
async def retry_invoice_emit(
    shopify_order_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    service = MiddlewareService(integration_repo=IntegrationRepository(session))
    return await service.retry_outbox_event(shopify_order_id, {"Factura.Insertar"})
