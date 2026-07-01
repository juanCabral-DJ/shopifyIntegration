from typing import Any
import httpx
import logging

from app.application.normalization import (
    records,
    first_int,
    first_value,
    error_message,
)
from app.application.ports import ExternalCatalogPort, IntegrationMappingPort, ShopifyCatalogPort
from app.infrastructure.se.client import ExternalSystemNotConfigured

logger = logging.getLogger(__name__)


class PaymentPollingService:
    def __init__(
        self,
        integration_repo: IntegrationMappingPort,
        shopify_client: ShopifyCatalogPort,
        external_client: ExternalCatalogPort,
    ) -> None:
        self.integration_repo = integration_repo
        self.shopify_client = shopify_client
        self.external_client = external_client

    async def payment_polling(self) -> dict[str, Any]:
        run = await self.integration_repo.start_sync_run("payment_polling")
        try:
            invoices = records(await self.external_client.get_invoices({"estado": "pagado"}))
            paid = 0
            skipped = 0
            for invoice in invoices:
                factrx_movil_id = str(first_value(invoice, "factrx_movil_id", "movil_id", "shopify_order_id") or "")
                if not factrx_movil_id:
                    skipped += 1
                    continue
                try:
                    shopify_order_id = int(factrx_movil_id)
                except ValueError:
                    skipped += 1
                    continue
                mapping = await self.integration_repo.get_order_map(shopify_order_id)
                if not mapping or mapping.status == "paid":
                    skipped += 1
                    continue
                amount = first_value(invoice, "eftrcb_monto", "amount", "factrx_total", "factrx_neto") or 0
                receipt_number = first_int(invoice, "eftrcb_numero", "recibo_numero", "factrx_numero") or shopify_order_id
                await self.shopify_client.update_order_financial_status(shopify_order_id, "paid")
                await self.integration_repo.upsert_receipt_map(
                    shopify_order_id=shopify_order_id,
                    eftrcb_numero=receipt_number,
                    amount=amount,
                    currency=first_value(invoice, "admmon_codigo", "currency"),
                    payment_source="se",
                    reference=str(first_value(invoice, "factrx_numero", "referencia") or ""),
                    balance_pending=first_value(invoice, "balance_pending", "pendiente"),
                    status="paid",
                )
                await self.integration_repo.upsert_order_map(
                    shopify_order_id=shopify_order_id,
                    shopify_order_name=mapping.shopify_order_name,
                    factrx_movil_id=None,
                    factrx_numero=mapping.factrx_numero,
                    status="paid",
                )
                paid += 1
            stats = {"received": len(invoices), "paid": paid, "skipped": skipped}
            await self.integration_repo.finish_sync_run(run, "success", stats)
            return {"status": "success", **stats}
        except (ExternalSystemNotConfigured, httpx.HTTPError, ValueError) as exc:
            message = error_message(exc)
            logger.exception("Payment polling failed")
            await self.integration_repo.finish_sync_run(run, "failed", error_message=message)
            return {"status": "failed", "error": message}
