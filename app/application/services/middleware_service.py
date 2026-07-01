from typing import Any
import logging

from app.core.config import settings
from app.application.ports import IntegrationMappingPort, ShopifyCatalogPort
from app.application.services.product_sync_service import ProductSyncService
from app.application.services.branch_sync_service import BranchSyncService
from app.application.services.price_sync_service import PriceSyncService
from app.application.services.inventory_sync_service import InventorySyncService
from app.application.services.customer_sync_service import CustomerSyncService
from app.application.services.taxonomy_sync_service import TaxonomySyncService
from app.application.services.image_sync_service import ImageSyncService
from app.application.services.invoice_sync_service import InvoiceSyncService
from app.application.services.payment_polling_service import PaymentPollingService
from app.infrastructure.se.client import SEClient
from app.infrastructure.shopify.client import ShopifyClient

logger = logging.getLogger(__name__)


class MiddlewareService:
    def __init__(
        self,
        integration_repo: IntegrationMappingPort,
        order_repo: Any = None,
        shopify_client: ShopifyCatalogPort | None = None,
        se_client: SEClient | None = None,
    ) -> None:
        self.integration_repo = integration_repo
        self.order_repo = order_repo
        self.shopify_client = shopify_client
        self.se_client = se_client

    def _require_se_client(self) -> SEClient:
        if not self.se_client:
            from app.core.config import settings
            self.se_client = SEClient(
                base_url=settings.se_base_url,
                api_key=settings.se_api_key,
                company_code=settings.se_company_code,
            )
        return self.se_client

    def _require_shopify_client(self) -> ShopifyClient:
        if not self.shopify_client:
            from app.core.config import settings
            self.shopify_client = ShopifyClient(
                shop=settings.shopify_shop,
                api_version=settings.shopify_api_version,
                access_token=settings.shopify_access_token,
            )
        return self.shopify_client

    async def register_shopify_event(self, topic: str, payload: dict[str, Any]) -> None:
        external_id = str(payload.get("id")) if payload.get("id") is not None else None
        event = await self.integration_repo.add_inbox_event(
            source="shopify",
            topic=topic,
            external_id=external_id,
            payload=payload,
            status="processing",
        )
        try:
            if topic in {"orders/create", "orders/updated", "orders/paid"} and payload.get("id"):
                invoice_service = InvoiceSyncService(
                    self.integration_repo,
                    self._require_shopify_client(),
                    self._require_se_client(),
                )
                invoice_payload, mapping_errors = await invoice_service.build_order_invoice_payload(payload)
                await self.integration_repo.upsert_order_map(
                    shopify_order_id=int(payload["id"]),
                    shopify_order_name=payload.get("name") or str(payload["id"]),
                    factrx_movil_id=None,
                    status="blocked_mapping" if mapping_errors else "received",
                )
                await self.integration_repo.add_outbox_event(
                    target="se",
                    operation="Factura.Insertar",
                    payload=invoice_payload,
                    status="blocked" if mapping_errors else "pending",
                )
            elif topic == "orders/cancelled" and payload.get("id"):
                await self.integration_repo.upsert_order_map(
                    shopify_order_id=int(payload["id"]),
                    shopify_order_name=payload.get("name") or str(payload["id"]),
                    factrx_movil_id=None,
                    status="cancelled",
                )
                await self.integration_repo.add_outbox_event(
                    target="se",
                    operation="Factura.cancel",
                    payload={"shopify_order_id": payload["id"], "factrx_movil_id": ""},
                )
            elif topic == "refunds/create":
                await self.integration_repo.add_outbox_event(
                    target="se",
                    operation="Factura.credit_note",
                    payload=payload,
                )
            elif topic == "fulfillments/create":
                await self.integration_repo.add_outbox_event(
                    target="se",
                    operation="inventario.fisico",
                    payload=payload,
                )
                await self.integration_repo.add_outbox_event(
                    target="se",
                    operation="Factura.InsertarVisita",
                    payload=payload,
                )
            elif topic in {"customers/create", "customers/update"}:
                await self.integration_repo.add_outbox_event(
                    target="se",
                    operation="mcxccte.Actualizar",
                    payload=payload,
                )
            await self.integration_repo.mark_inbox_done(event)
        except Exception as exc:
            await self.integration_repo.mark_inbox_failed(event, str(exc))
            raise

    async def sync_products(self, payload: Any = None, run: Any | None = None) -> dict[str, Any]:
        return await ProductSyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).sync_products(payload=payload, run=run)

    async def sync_prices(self, run: Any | None = None) -> dict[str, Any]:
        return await PriceSyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).sync_prices(run=run)

    async def sync_inventory(
        self,
        payload: Any = None,
        reconcile: bool = False,
        run: Any | None = None,
    ) -> dict[str, Any]:
        return await InventorySyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).sync_inventory(payload=payload, reconcile=reconcile, run=run)

    async def proxy_report(self, report: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._require_se_client().post(f"/api/Factura/{report}", payload)

    async def sync_images(self, run: Any | None = None) -> dict[str, Any]:
        return await ImageSyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).sync_images(run=run)

    async def sync_branches(self) -> dict[str, Any]:
        return await BranchSyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).sync_branches()

    async def sync_customers(self) -> dict[str, Any]:
        return await CustomerSyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).sync_customers()

    async def import_se_customer_to_shopify(self, customer: dict[str, Any]) -> dict[str, Any]:
        return await CustomerSyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).import_se_customer_to_shopify(customer)

    async def sync_catalog_taxonomy(self) -> dict[str, Any]:
        return await TaxonomySyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).sync_catalog_taxonomy()

    async def send_invoice(self, payload: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        return await InvoiceSyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).send_invoice(payload)

    async def send_invoice_visit(self, payload: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        return await InvoiceSyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).send_invoice_visit(payload)

    async def retry_order_invoice(self, shopify_order_id: int) -> dict[str, Any]:
        return await InvoiceSyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).retry_order_invoice(shopify_order_id)

    async def retry_outbox_event(self, shopify_order_id: int, operations: set[str]) -> dict[str, Any]:
        return await InvoiceSyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).retry_outbox_event(shopify_order_id, operations)

    async def payment_polling(self) -> dict[str, Any]:
        return await PaymentPollingService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).payment_polling()

    async def _build_order_invoice_payload(self, order: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        return await InvoiceSyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).build_order_invoice_payload(order)

    async def process_pending_outbox(self, limit: int = 50) -> dict[str, Any]:
        processed = 0
        done = 0
        failed = 0
        events = await self.integration_repo.list_due_outbox(limit=limit)
        invoice_service = InvoiceSyncService(
            self.integration_repo,
            self._require_shopify_client(),
            self._require_se_client(),
        )
        for event in events:
            await self.integration_repo.mark_outbox_processing(event)
            session = getattr(self.integration_repo, "session", None)
            if session is not None:
                await self.session_commit_safe(session)
            try:
                from app.application.normalization import error_message as normal_err
                response = await invoice_service._dispatch_outbox_event(event.operation, event.payload or {})
                await self.integration_repo.mark_outbox_done(event, response)
                done += 1
                if session is not None:
                    await self.session_commit_safe(session)
            except Exception as exc:
                from app.application.normalization import error_message as normal_err
                message = normal_err(exc)
                logger.exception("Outbox event failed: %s", event.operation)
                await self.integration_repo.mark_outbox_failed(event, message)
                failed += 1
                if session is not None:
                    await self.session_commit_safe(session)
            processed += 1
        return {"status": "success", "processed": processed, "done": done, "failed": failed}

    async def session_commit_safe(self, session: Any) -> None:
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Helper aliases for backward compatibility (primarily used in tests)
from app.application.normalization import records as _records
from app.application.services.invoice_sync_service import (
    invoice_rows as _invoice_rows,
    invoice_visit_rows as _invoice_visit_rows,
)
from app.application.transformers.se_to_shopify import se_customer_to_shopify as _se_customer_to_shopify

