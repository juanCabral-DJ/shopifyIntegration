import logging
from typing import Any
import httpx

from app.application.services.branch_sync_service import BranchSyncService
from app.application.services.product_sync_service import ProductSyncService
from app.application.transformers.se_to_shopify import (
    se_customer_to_shopify,
    shopify_customer_to_se,
    shopify_product_payload as se_shopify_product_payload,
)
from app.application.transformers.shopify_to_se import order_to_mfactrx_rows
from app.core.config import settings
from app.infrastructure.repositories.integration_repository import IntegrationRepository
from app.infrastructure.repositories.order_repository import OrderRepository
from app.infrastructure.se.client import ExternalSystemNotConfigured, SEClient
from app.infrastructure.shopify.client import ShopifyClient

logger = logging.getLogger(__name__)


class MiddlewareService:
    def __init__(
        self,
        integration_repo: IntegrationRepository,
        order_repo: OrderRepository | None = None,
        shopify_client: ShopifyClient | None = None,
        se_client: SEClient | None = None,
    ) -> None:
        self.integration_repo = integration_repo
        self.order_repo = order_repo
        self.shopify_client = shopify_client
        self.se_client = se_client

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
                invoice_payload, mapping_errors = await self._build_order_invoice_payload(payload)
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

    async def sync_prices(self) -> dict[str, Any]:
        run = await self.integration_repo.start_sync_run("prices")
        try:
            data = await self._require_se_client().list_prices()
            prices = _records(data)
            principal_prices = _principal_prices_by_item(prices)
            mapped = 0
            shopify_updated = 0
            skipped = 0
            for item_code, price in principal_prices.items():
                amount = _first_value(price, "facpre_Contado", "facpre_contado")
                existing = await self.integration_repo.get_sku_map_by_item_code(item_code)
                if existing is None:
                    skipped += 1
                    await self.integration_repo.upsert_sku_map(
                        invitm_codigo=item_code,
                        sku=str(item_code),
                        last_price=amount,
                        active=True,
                    )
                    mapped += 1
                    continue
                if (
                    _positive_int(getattr(existing, "shopify_product_id", None)) is not None
                    and _positive_int(getattr(existing, "shopify_variant_id", None)) is not None
                    and not _prices_equal(getattr(existing, "last_price", None), amount)
                ):
                    await self._require_shopify_client().update_product(
                        int(existing.shopify_product_id),
                        {
                            "variants": [
                                {
                                    "id": int(existing.shopify_variant_id),
                                    "price": _shopify_price(amount),
                                }
                            ]
                        },
                    )
                    shopify_updated += 1
                await self.integration_repo.upsert_sku_map(
                    invitm_codigo=item_code,
                    sku=existing.sku if existing else str(item_code),
                    last_price=amount,
                    active=existing.active if existing else True,
                )
                mapped += 1
            await self.integration_repo.add_outbox_event(
                target="shopify",
                operation="prices.sync",
                payload={
                    "source": "se",
                    "received": len(prices),
                    "mapped": mapped,
                    "shopify_updated": shopify_updated,
                    "skipped": skipped,
                },
                status="done",
            )
            stats = {
                "received": len(prices),
                "mapped": mapped,
                "shopify_updated": shopify_updated,
                "skipped": skipped,
            }
            await self.integration_repo.finish_sync_run(run, "success", stats)
            return {"status": "success", **stats}
        except (ExternalSystemNotConfigured, httpx.HTTPError) as exc:
            await self.integration_repo.finish_sync_run(run, "failed", error_message=str(exc))
            return {"status": "failed", "error": str(exc)}

    async def sync_inventory(
        self,
        payload: Any = None,
        reconcile: bool = False,
        run: Any | None = None,
    ) -> dict[str, Any]:
        run = run or await self.integration_repo.start_sync_run("inventory_reconcile" if reconcile else "inventory")
        try:
            products = await self._require_se_client().list_products(payload)
            product_records = _records(products)
            physical = await self._require_se_client().list_physical_inventory() if reconcile else []
            physical_records = _records(physical)
            physical_by_item = {
                item_code: record
                for record in physical_records
                if (item_code := _first_int(record, "invitm_codigo", "invitm_Codigo", "codigo")) is not None
            }
            snapshots = 0
            inventory_updated = 0
            inventory_skipped = 0
            discrepancies = 0
            location_id = await self._default_shopify_location_id()
            for processed, product in enumerate(product_records, start=1):
                item_code = _first_int(product, "invitm_codigo", "invitm_Codigo", "codigo")
                if item_code is None:
                    inventory_skipped += 1
                    await self._update_inventory_sync_progress(
                        run,
                        processed,
                        len(product_records),
                        len(physical_records),
                        snapshots,
                        inventory_updated,
                        inventory_skipped,
                        discrepancies,
                        reconcile,
                    )
                    continue
                stock = _first_value(product, "se_stock", "stock", "existencia", "invitm_existencia") or 0
                stock = _first_value(product, "invcos_Exist", "invcos_exist", "se_stock", "stock", "existencia", "invitm_existencia") or 0
                physical_record = physical_by_item.get(item_code)
                mapping = await self.integration_repo.get_sku_map_by_item_code(item_code)
                if mapping is None or not mapping.shopify_inventory_item_id:
                    shopify_product = await self._upsert_shopify_product(product, mapping)
                    variant = _first_variant(shopify_product)
                    mapping = await self.integration_repo.upsert_sku_map(
                        invitm_codigo=item_code,
                        sku=_product_sku(product, item_code),
                        shopify_product_id=_first_int(shopify_product, "id"),
                        shopify_variant_id=_first_int(variant, "id"),
                        shopify_inventory_item_id=_first_int(variant, "inventory_item_id"),
                        last_price=_product_price(product),
                        active=bool(_first_value(product, "activo", "active", "admsts_codigo") in (None, True, 1, "1", "A")),
                    )
                if mapping.shopify_inventory_item_id and location_id is not None:
                    final_stock = _stock_quantity(stock)
                    await self._require_shopify_client().set_inventory_level(
                        int(mapping.shopify_inventory_item_id),
                        location_id,
                        final_stock,
                    )
                    inventory_updated += 1
                else:
                    inventory_skipped += 1
                mobile_stock = (
                    _first_value(physical_record, "cantidad_fisica", "cantidad", "stock")
                    if physical_record
                    else None
                )
                if reconcile and mobile_stock is not None:
                    difference = abs(_stock_quantity(mobile_stock) - _stock_quantity(stock))
                    if difference > settings.inventory_discrepancy_threshold:
                        discrepancies += 1
                        await self.integration_repo.add_outbox_event(
                            target="internal",
                            operation="alert.inventory_discrepancy",
                            payload={
                                "invitm_codigo": item_code,
                                "se_stock": _stock_quantity(stock),
                                "mobile_physical_stock": _stock_quantity(mobile_stock),
                                "difference": difference,
                            },
                        )
                await self.integration_repo.add_inventory_snapshot(
                    invitm_codigo=item_code,
                    se_stock=stock,
                    admsuc_codigo=_first_int(product, "admsuc_codigo", "admsuc_Codigo"),
                    mobile_physical_stock=mobile_stock,
                    reconciled=reconcile,
                    source_payload=product,
                )
                snapshots += 1
                await self._update_inventory_sync_progress(
                    run,
                    processed,
                    len(product_records),
                    len(physical_records),
                    snapshots,
                    inventory_updated,
                    inventory_skipped,
                    discrepancies,
                    reconcile,
                )
            stats = {
                "products_received": len(product_records),
                "physical_counts_received": len(physical_records),
                "snapshots": snapshots,
                "shopify_inventory_updated": inventory_updated,
                "shopify_inventory_skipped": inventory_skipped,
                "discrepancies": discrepancies,
                "reconcile": reconcile,
            }
            await self.integration_repo.finish_sync_run(run, "success", stats)
            return {"status": "success", **stats}
        except (ExternalSystemNotConfigured, httpx.HTTPError, ValueError) as exc:
            message = _error_message(exc)
            logger.exception("Inventory sync failed")
            await self.integration_repo.finish_sync_run(run, "failed", error_message=message)
            return {"status": "failed", "error": message}

    async def _update_inventory_sync_progress(
        self,
        run: Any,
        processed: int,
        products_received: int,
        physical_counts_received: int,
        snapshots: int,
        inventory_updated: int,
        inventory_skipped: int,
        discrepancies: int,
        reconcile: bool,
    ) -> None:
        if processed % 100 != 0:
            return
        update_stats = getattr(self.integration_repo, "update_sync_run_stats", None)
        if update_stats is None:
            return
        await update_stats(
            run,
            {
                "products_received": products_received,
                "physical_counts_received": physical_counts_received,
                "processed": processed,
                "snapshots": snapshots,
                "shopify_inventory_updated": inventory_updated,
                "shopify_inventory_skipped": inventory_skipped,
                "discrepancies": discrepancies,
                "reconcile": reconcile,
            },
        )
        session = getattr(self.integration_repo, "session", None)
        if session is not None:
            await session.commit()

    async def proxy_report(self, report: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if report == "sales-by-family":
            data = await self._require_se_client().sales_by_family(payload)
        elif report == "sales-by-family-detail":
            data = await self._require_se_client().sales_by_family_detail(payload)
        elif report == "purchased-products":
            data = await self._require_se_client().purchased_products(payload)
        elif report == "total-collections":
            data = await self._require_se_client().total_collections(payload)
        else:
            raise ValueError("Unknown report")
        return {"report": report, "data": data}

    async def sync_images(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        run = await self.integration_repo.start_sync_run("images")
        try:
            requested_item = _first_int(payload or {}, "invitm_codigo", "admimg_master")
            mappings = await self.integration_repo.list_mapping("skus", limit=1000)
            uploaded = 0
            skipped = 0
            received = 0
            for mapping in mappings:
                item_code = getattr(mapping, "invitm_codigo", None)
                if requested_item is not None and item_code != requested_item:
                    continue
                shopify_product_id = getattr(mapping, "shopify_product_id", None)
                if not shopify_product_id:
                    skipped += 1
                    continue
                images = _records(await self._require_se_client().list_images("INVITM", int(item_code)))
                received += len(images)
                for index, image in enumerate(images, start=1):
                    base64_data = _first_value(image, "base64", "admimg_imagen", "imagen", "image", "attachment")
                    if not base64_data:
                        skipped += 1
                        continue
                    filename = str(_first_value(image, "filename", "admimg_nombre", "nombre") or f"{item_code}-{index}.jpg")
                    await self._require_shopify_client().upload_product_image(
                        int(shopify_product_id),
                        str(base64_data),
                        filename,
                    )
                    uploaded += 1
            stats = {"received": received, "uploaded": uploaded, "skipped": skipped}
            await self.integration_repo.finish_sync_run(run, "success", stats)
            return {"status": "success", **stats}
        except (ExternalSystemNotConfigured, httpx.HTTPError, ValueError) as exc:
            message = _error_message(exc)
            logger.exception("Image sync failed")
            await self.integration_repo.finish_sync_run(run, "failed", error_message=message)
            return {"status": "failed", "error": message}

    async def sync_branches(self) -> dict[str, Any]:
        return await BranchSyncService(
            integration_repo=self.integration_repo,
            shopify_client=self._require_shopify_client(),
            external_client=self._require_se_client(),
        ).sync_branches()

    async def sync_customers(self) -> dict[str, Any]:
        run = await self.integration_repo.start_sync_run("customers")
        try:
            customers = _records(await self._require_se_client().list_customers())
            mapped = 0
            for customer in customers:
                customer_code = _first_int(customer, "cxccte_Codigo", "cxccte_codigo", "codigo")
                if customer_code is None:
                    continue
                payload = se_customer_to_shopify(customer)
                existing = await self.integration_repo.upsert_customer_map(
                    cxccte_codigo=customer_code,
                    email=payload.get("email"),
                    phone=payload.get("phone"),
                )
                if existing.shopify_customer_id:
                    shopify_customer = await self._require_shopify_client().update_customer(
                        int(existing.shopify_customer_id),
                        payload,
                    )
                else:
                    shopify_customer = await self._require_shopify_client().create_customer(payload)
                await self.integration_repo.upsert_customer_map(
                    cxccte_codigo=customer_code,
                    shopify_customer_id=_first_int(shopify_customer, "id"),
                    email=shopify_customer.get("email") or payload.get("email"),
                    phone=shopify_customer.get("phone") or payload.get("phone"),
                )
                mapped += 1
            await self.integration_repo.finish_sync_run(run, "success", {"received": len(customers), "mapped": mapped})
            return {"status": "success", "received": len(customers), "mapped": mapped}
        except (ExternalSystemNotConfigured, httpx.HTTPError, ValueError) as exc:
            message = _error_message(exc)
            logger.exception("Customer sync failed")
            await self.integration_repo.finish_sync_run(run, "failed", error_message=message)
            return {"status": "failed", "error": message}

    async def import_se_customer_to_shopify(self, customer: dict[str, Any]) -> dict[str, Any]:
        customer_code = _first_int(customer, "cxccte_Codigo", "cxccte_codigo", "codigo")
        if customer_code is None:
            return {"status": "failed", "error": "cxccte_Codigo is required"}

        await self.integration_repo.set_param_cache(f"se_customer:{customer_code}", customer)
        existing_map = await self.integration_repo.upsert_customer_map(
            cxccte_codigo=customer_code,
            email=_se_customer_email(customer),
            phone=_normalize_phone(_first_value(customer, "cxccte_telef1", "cxccte_Telef1", "telefono", "phone")),
        )
        shopify_payload = se_customer_to_shopify(customer)
        if existing_map.shopify_customer_id:
            shopify_customer = await self._require_shopify_client().update_customer(
                int(existing_map.shopify_customer_id),
                shopify_payload,
            )
            action = "updated"
        else:
            shopify_customer = await self._require_shopify_client().create_customer(shopify_payload)
            action = "created"

        shopify_customer_id = _first_int(shopify_customer, "id")
        if shopify_customer_id is None:
            return {"status": "failed", "error": "Shopify response did not include customer id"}
        await self.integration_repo.upsert_customer_map(
            cxccte_codigo=customer_code,
            shopify_customer_id=shopify_customer_id,
            email=shopify_customer.get("email") or _se_customer_email(customer),
            phone=shopify_customer.get("phone") or _normalize_phone(
                _first_value(customer, "cxccte_telef1", "cxccte_Telef1", "telefono", "phone")
            ),
        )
        await self.integration_repo.add_outbox_event(
            target="shopify",
            operation=f"customers.{action}",
            payload={
                "cxccte_codigo": customer_code,
                "shopify_customer_id": shopify_customer_id,
                "source": "se_manual",
            },
            status="done",
        )
        return {
            "status": "success",
            "action": action,
            "cxccte_codigo": customer_code,
            "shopify_customer_id": shopify_customer_id,
        }

    async def sync_catalog_taxonomy(self) -> dict[str, Any]:
        run = await self.integration_repo.start_sync_run("catalog_taxonomy")
        try:
            families = _records(await self._require_se_client().list_families())
            brands = _records(await self._require_se_client().list_brands())
            created_collections = 0
            existing_collections = 0
            seen_family_names: set[str] = set()
            for family in families:
                family_id = str(_first_value(family, "invfam_codigo", "familia_codigo", "codigo", "id") or "")
                family_name = _clean_text(_first_value(family, "invfam_nombre", "familia_nombre", "nombre", "name"))
                if family_id:
                    shopify_collection_id = None
                    if family_name:
                        normalized_family_name = family_name.strip().casefold()
                        if normalized_family_name in seen_family_names:
                            continue
                        seen_family_names.add(normalized_family_name)
                        shopify_client = self._require_shopify_client()
                        if hasattr(shopify_client, "get_or_create_custom_collection"):
                            collection = await shopify_client.get_or_create_custom_collection(family_name)
                        else:
                            collection = await shopify_client.ensure_custom_collection(family_name)
                        shopify_collection_id = _first_int(collection, "id")
                        if collection.get("sync_status") == "created":
                            created_collections += 1
                        else:
                            existing_collections += 1
                    await self.integration_repo.upsert_family_map(
                        se_familia_id=family_id,
                        se_familia_nombre=family_name,
                        shopify_collection_id=shopify_collection_id,
                    )
            for brand in brands:
                brand_id = str(_first_value(brand, "invmar_codigo", "marca_codigo", "codigo", "id") or "")
                brand_name = _first_value(brand, "invmar_nombre", "marca_nombre", "nombre", "name")
                if brand_id:
                    await self.integration_repo.upsert_brand_map(
                        se_marca_id=brand_id,
                        se_marca_nombre=brand_name,
                        shopify_tag=str(brand_name or brand_id),
                    )
            stats = {
                "families": len(families),
                "brands": len(brands),
                "collections_created": created_collections,
                "collections_existing": existing_collections,
            }
            await self.integration_repo.finish_sync_run(run, "success", stats)
            return {"status": "success", **stats}
        except (ExternalSystemNotConfigured, httpx.HTTPError) as exc:
            await self.integration_repo.finish_sync_run(run, "failed", error_message=str(exc))
            return {"status": "failed", "error": str(exc)}

    async def process_pending_outbox(self, limit: int = 50) -> dict[str, Any]:
        processed = 0
        done = 0
        failed = 0
        events = await self.integration_repo.list_due_outbox(limit=limit)
        for event in events:
            await self.integration_repo.mark_outbox_processing(event)
            session = getattr(self.integration_repo, "session", None)
            if session is not None:
                await session.commit()
            try:
                response = await self._dispatch_outbox_event(event.operation, event.payload or {})
                await self.integration_repo.mark_outbox_done(event, response)
                done += 1
                if session is not None:
                    await session.commit()
            except (ExternalSystemNotConfigured, httpx.HTTPError, ValueError) as exc:
                message = _error_message(exc)
                logger.exception("Outbox event failed: %s", event.operation)
                await self.integration_repo.mark_outbox_failed(event, message)
                failed += 1
                if session is not None:
                    await session.commit()
            processed += 1
        return {"status": "success", "processed": processed, "done": done, "failed": failed}

    async def payment_polling(self) -> dict[str, Any]:
        run = await self.integration_repo.start_sync_run("payment_polling")
        try:
            invoices = _records(await self._require_se_client().get_invoices({"estado": "pagado"}))
            paid = 0
            skipped = 0
            for invoice in invoices:
                factrx_movil_id = str(_first_value(invoice, "factrx_movil_id", "movil_id", "shopify_order_id") or "")
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
                amount = _first_value(invoice, "eftrcb_monto", "amount", "factrx_total", "factrx_neto") or 0
                receipt_number = _first_int(invoice, "eftrcb_numero", "recibo_numero", "factrx_numero") or shopify_order_id
                await self._require_shopify_client().update_order_financial_status(shopify_order_id, "paid")
                await self.integration_repo.upsert_receipt_map(
                    shopify_order_id=shopify_order_id,
                    eftrcb_numero=receipt_number,
                    amount=amount,
                    currency=_first_value(invoice, "admmon_codigo", "currency"),
                    payment_source="se",
                    reference=str(_first_value(invoice, "factrx_numero", "referencia") or ""),
                    balance_pending=_first_value(invoice, "balance_pending", "pendiente"),
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
            message = _error_message(exc)
            logger.exception("Payment polling failed")
            await self.integration_repo.finish_sync_run(run, "failed", error_message=message)
            return {"status": "failed", "error": message}

    async def retry_order_invoice(self, shopify_order_id: int) -> dict[str, Any]:
        return await self.retry_outbox_event(shopify_order_id, {"Factura.Insertar"})

    async def retry_outbox_event(self, shopify_order_id: int, operations: set[str]) -> dict[str, Any]:
        event = await self.integration_repo.reset_outbox_for_retry(shopify_order_id, operations)
        if event is None:
            return {"status": "not_found", "detail": "No retryable outbox event found"}
        return _outbox_event_response(event)

    async def send_invoice(self, payload: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        rows = _invoice_rows(payload)
        if not rows:
            return {"status": "failed", "error": "Invoice payload must include at least one mfactrx row"}
        response = await self._process_invoice_insert(payload)
        await self.integration_repo.add_outbox_event(
            target="se",
            operation="Factura.Insertar",
            payload=rows,
            status="done",
        )
        return {"status": "success", "sent": len(rows), "response": response}

    async def send_invoice_visit(self, payload: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        rows = _invoice_visit_rows(payload)
        if not rows:
            return {"status": "failed", "error": "Invoice visit payload must include at least one row"}
        response = await self._require_se_client().insert_invoice_visit(rows)
        await self.integration_repo.add_outbox_event(
            target="se",
            operation="Factura.InsertarVisita",
            payload=rows,
            status="done",
        )
        return {"status": "success", "sent": len(rows), "response": response}

    async def _dispatch_outbox_event(self, operation: str, payload: dict[str, Any]) -> Any:
        if operation == "Factura.Insertar":
            return await self._process_invoice_insert(payload)
        if operation == "Factura.cancel":
            response = await self._require_se_client().post("/api/Factura/Cancelar", payload)
            shopify_order_id = _first_int(payload, "shopify_order_id", "id")
            if shopify_order_id is not None:
                mapping = await self.integration_repo.get_order_map(shopify_order_id)
                await self.integration_repo.upsert_order_map(
                    shopify_order_id=shopify_order_id,
                    shopify_order_name=getattr(mapping, "shopify_order_name", str(shopify_order_id)),
                    factrx_movil_id=None,
                    status="cancelled",
                )
            return response
        if operation == "Factura.credit_note":
            return await self._require_se_client().post("/api/NotaCredito/Insertar", payload)
        if operation == "inventario.fisico":
            return await self._require_se_client().update_physical_inventory(_fulfillment_inventory_payload(payload))
        if operation == "Factura.InsertarVisita":
            return await self._require_se_client().insert_invoice_visit(_invoice_visit_rows(payload))
        if operation == "mcxccte.Actualizar":
            return await self._require_se_client().update_customer(shopify_customer_to_se(payload))
        if operation == "products.sync":
            return await self.sync_products(payload)
        if operation == "prices.sync":
            return await self.sync_prices()
        if operation == "alert.inventory_discrepancy":
            return {"acknowledged": True, "payload": payload}
        raise ValueError(f"Unsupported outbox operation: {operation}")

    async def _process_invoice_insert(self, payload: dict[str, Any]) -> Any:
        se_client = self._require_se_client()
        response = await se_client.insert_invoice(payload)
        se_status_code = getattr(se_client, "last_status_code", None)
        shopify_order_id = _first_int(payload, "shopify_order_id")
        if shopify_order_id is None:
            first_row = _invoice_rows(payload)[0] if _invoice_rows(payload) else {}
            shopify_order_id = _first_int(first_row, "factrx_movil_id")
        shopify_response = None
        if shopify_order_id is not None:
            factrx_numero = str(_first_value(response if isinstance(response, dict) else {}, "factrx_numero", "numero") or "")
            if not factrx_numero:
                rows = _invoice_rows(payload)
                factrx_numero = str(_first_value(rows[0] if rows else {}, "factrx_numero") or shopify_order_id)
            mapping = await self.integration_repo.get_order_map(shopify_order_id)
            await self.integration_repo.upsert_order_map(
                shopify_order_id=shopify_order_id,
                shopify_order_name=getattr(mapping, "shopify_order_name", str(shopify_order_id)),
                factrx_movil_id=None,
                factrx_numero=factrx_numero,
                status="invoiced",
            )
            await self.integration_repo.upsert_invoice_map(
                shopify_order_id=shopify_order_id,
                factrx_numero=factrx_numero,
                status="invoiced",
                payload=payload,
                ncf=str(_first_value(response if isinstance(response, dict) else {}, "ncf") or "") or None,
            )
            if se_status_code == 200:
                try:
                    shopify_response = await self._mark_shopify_order_paid_and_fulfilled(shopify_order_id)
                except Exception as exc:
                    logger.exception("Shopify update failed after SE invoice insert")
                    shopify_response = {"status": "failed", "error": _error_message(exc)}
        if shopify_response is None:
            return response
        return {"invoice": response, "shopify": shopify_response}

    async def _mark_shopify_order_paid_and_fulfilled(self, shopify_order_id: int) -> dict[str, Any]:
        if self.shopify_client is None:
            return {"status": "skipped", "reason": "shopify_client_not_available"}
        payment_response = None
        if hasattr(self.shopify_client, "create_manual_payment_transaction"):
            order = await self.shopify_client.get_order(shopify_order_id)
            if str(order.get("financial_status") or "").lower() == "paid":
                payment_response = {"status": "skipped", "reason": "already_paid"}
            else:
                amount = _positive_float(order.get("total_outstanding")) or _positive_float(order.get("total_price"))
                if amount is None:
                    raise ValueError("Shopify order total must be greater than zero to mark as paid")
                payment_response = await self.shopify_client.create_manual_payment_transaction(
                    shopify_order_id,
                    amount,
                    str(order.get("currency") or "USD"),
                    gateway="manual",
                )
        elif hasattr(self.shopify_client, "update_order_financial_status"):
            payment_response = await self.shopify_client.update_order_financial_status(shopify_order_id, "paid")
        fulfillment_response = await self._fulfill_shopify_order_after_invoice(shopify_order_id)
        return {
            "status": "paid_and_fulfilled",
            "payment": payment_response,
            "fulfillment": fulfillment_response,
        }

    async def _fulfill_shopify_order_after_invoice(self, shopify_order_id: int) -> dict[str, Any]:
        if self.shopify_client is None:
            return {"status": "skipped", "reason": "shopify_client_not_available"}
        if not hasattr(self.shopify_client, "fulfill_order"):
            return {"status": "skipped", "reason": "fulfill_order_not_supported"}
        return await self.shopify_client.fulfill_order(shopify_order_id)

    async def _upsert_shopify_product(
        self,
        product: dict[str, Any],
        existing_mapping: Any | None = None,
        shopify_variant_index: dict[str, tuple[dict[str, Any], dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        item_code = _first_int(product, "invitm_codigo", "invitm_Codigo", "invitmCodigo", "codigo")
        if item_code is None:
            raise ValueError("Product item code is required")
        sku = _product_sku(product, item_code)
        payload = se_shopify_product_payload(product)
        shopify_client = self._require_shopify_client()
        product_id = _positive_int(getattr(existing_mapping, "shopify_product_id", None))
        variant_id = _positive_int(getattr(existing_mapping, "shopify_variant_id", None))

        if product_id is None:
            found = (
                shopify_variant_index.get(sku.strip().casefold())
                if shopify_variant_index is not None
                else await shopify_client.find_product_variant_by_sku(sku)
            )
            if found:
                found_product, _variant = found
                product_id = _first_int(found_product, "id")
                variant_id = _first_int(_variant, "id")

        if product_id is not None:
            if variant_id is not None and payload.get("variants"):
                payload["variants"][0]["id"] = variant_id
            updated = await shopify_client.update_product(product_id, payload)
            updated["sync_status"] = "updated"
            return updated

        created = await shopify_client.create_product(payload)
        created["sync_status"] = "created"
        return created

    async def _shopify_variant_index(self) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
        index: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        for product in await self._require_shopify_client().list_products():
            for variant in product.get("variants") or []:
                sku = str(variant.get("sku") or "").strip().casefold()
                if sku and sku not in index:
                    index[sku] = (product, variant)
        return index

    async def _ensure_product_collection(self, product: dict[str, Any], shopify_product: dict[str, Any]) -> None:
        family_name = _clean_text(_first_value(product, "invfam_nombre", "familia_nombre", "product_type"))
        product_id = _first_int(shopify_product, "id")
        if not family_name or product_id is None:
            return
        family_map = await self.integration_repo.get_family_map_by_name(family_name)
        collection_id = _positive_int(getattr(family_map, "shopify_collection_id", None)) if family_map else None
        if collection_id is not None:
            await self._require_shopify_client().ensure_collect(product_id, collection_id)

    async def _default_shopify_location_id(self) -> int | None:
        branch = await self.integration_repo.get_first_branch_map_with_location()
        if branch and branch.shopify_location_id:
            return int(branch.shopify_location_id)
        locations = await self._require_shopify_client().list_locations()
        for location in locations:
            if location.get("active", True) and location.get("id") is not None:
                return int(location["id"])
        return None

    async def _shopify_locations_by_name(self) -> dict[str, dict[str, Any]]:
        locations: dict[str, dict[str, Any]] = {}
        for location in await self._require_shopify_client().list_locations():
            normalized_name = str(location.get("name") or "").strip().casefold()
            if normalized_name and normalized_name not in locations:
                locations[normalized_name] = location
        return locations

    async def _ensure_shopify_location(
        self,
        branch: dict[str, Any],
        branch_name: str,
        shopify_locations_by_name: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_name = branch_name.strip().casefold()
        existing_location = shopify_locations_by_name.get(normalized_name)
        if existing_location:
            result = dict(existing_location)
            result["sync_status"] = "exists"
            return result

        created = await self._require_shopify_client().create_location(_shopify_location_payload(branch, branch_name))
        if normalized_name:
            shopify_locations_by_name[normalized_name] = created
        return created

    def _require_se_client(self) -> SEClient:
        if not self.se_client:
            raise ExternalSystemNotConfigured("SE client dependency is not available")
        return self.se_client

    def _require_shopify_client(self) -> ShopifyClient:
        if not self.shopify_client:
            raise ExternalSystemNotConfigured("Shopify client dependency is not available")
        return self.shopify_client

    async def _build_order_invoice_payload(self, order: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        defaults = await self._se_invoice_defaults()
        mapping_errors: list[str] = []
        customer_code = await self._resolve_customer_code(order)
        if customer_code is None:
            customer_code = _positive_int(defaults.get("cxccte_codigo"))

        branch_code = await self._resolve_branch_code(order, defaults)
        vendor_code = _positive_int(defaults.get("facvdr_codigo"))
        receipt_type_code = _positive_int(defaults.get("admtco_codigo"))
        price_list_code = _positive_int(defaults.get("facpre_codigo"))

        variant_map, sku_map, item_errors = await self._resolve_line_item_codes(order)
        mapping_errors.extend(item_errors)
        line_branch_codes = await self._resolve_line_item_branch_codes(order, variant_map, sku_map)
        invoice_payload = {
            "shopify_order_id": order["id"],
            "mfactrx_rows": order_to_mfactrx_rows(
                order,
                company_code=settings.se_company_code,
                branch_code=branch_code,
                customer_code=customer_code,
                vendor_code=vendor_code,
                receipt_type_code=receipt_type_code,
                price_list_code=price_list_code,
                ncf_serial=defaults.get("admncf_serial"),
                variant_to_item_code=variant_map,
                sku_to_item_code=sku_map,
                line_item_branch_codes=line_branch_codes,
            ),
            "mapping_errors": mapping_errors,
            "mapping_context": {
                "branch_code": branch_code,
                "line_branch_codes": line_branch_codes,
                "customer_code": customer_code,
                "vendor_code": vendor_code,
                "receipt_type_code": receipt_type_code,
                "price_list_code": price_list_code,
            },
        }
        return invoice_payload, mapping_errors

    async def _se_invoice_defaults(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {}
        for key in ("se_defaults", "factura_insertar_defaults"):
            cached = await self.integration_repo.get_param_cache(key)
            if cached and isinstance(cached.value, dict):
                defaults.update(cached.value)
        for key in ("admsuc_codigo", "cxccte_codigo", "facvdr_codigo", "admtco_codigo", "facpre_codigo", "admncf_serial"):
            cached = await self.integration_repo.get_param_cache(key)
            if cached:
                value = cached.value.get("value") if isinstance(cached.value, dict) else cached.value
                defaults[key] = value
        return defaults

    async def _resolve_customer_code(self, order: dict[str, Any]) -> int | None:
        customer = order.get("customer") or {}
        customer_id = _positive_int(customer.get("id"))
        if customer_id is not None:
            mapping = await self.integration_repo.get_customer_map_by_shopify_id(customer_id)
            if mapping:
                return mapping.cxccte_codigo
        for email in (customer.get("email"), order.get("email"), order.get("contact_email")):
            if email:
                mapping = await self.integration_repo.get_customer_map_by_email(str(email))
                if mapping:
                    return mapping.cxccte_codigo
        for phone in (customer.get("phone"), order.get("phone")):
            if phone:
                mapping = await self.integration_repo.get_customer_map_by_phone(str(phone))
                if mapping:
                    return mapping.cxccte_codigo
        return None

    async def _resolve_branch_code(
        self,
        order: dict[str, Any],
        defaults: dict[str, Any],
    ) -> int | None:
        for tag in _shopify_tags(order):
            get_by_name = getattr(self.integration_repo, "get_branch_map_by_name", None)
            if get_by_name is None:
                break
            mapping = await get_by_name(tag)
            if mapping:
                return mapping.admsuc_codigo

        location_id = _positive_int(order.get("location_id"))
        if location_id is not None:
            mapping = await self.integration_repo.get_branch_map_by_shopify_location_id(location_id)
            if mapping:
                return mapping.admsuc_codigo
        return _positive_int(defaults.get("admsuc_codigo"))

    async def _resolve_line_item_codes(
        self,
        order: dict[str, Any],
    ) -> tuple[dict[int, int], dict[str, int], list[str]]:
        variant_map: dict[int, int] = {}
        sku_map: dict[str, int] = {}
        errors: list[str] = []
        for item in order.get("line_items") or []:
            variant_id = _positive_int(item.get("variant_id"))
            sku = str(item.get("sku") or "").strip()
            mapping = None
            if variant_id is not None:
                mapping = await self.integration_repo.get_sku_map_by_variant_id(variant_id)
            if mapping is None and sku:
                mapping = await self.integration_repo.get_sku_map_by_sku(sku)
            if mapping:
                if variant_id is not None:
                    variant_map[variant_id] = mapping.invitm_codigo
                if sku:
                    sku_map[sku] = mapping.invitm_codigo
                continue
            label = sku or item.get("name") or item.get("title") or "line_item"
            errors.append(f"Falta mapeo de producto Shopify '{label}' -> invitm_codigo.")
        return variant_map, sku_map, errors

    async def _resolve_line_item_branch_codes(
        self,
        order: dict[str, Any],
        variant_map: dict[int, int],
        sku_map: dict[str, int],
    ) -> dict[int, int]:
        get_inventory = getattr(self.integration_repo, "get_latest_inventory_with_stock", None)
        if get_inventory is None:
            return {}

        line_branch_codes: dict[int, int] = {}
        normalized_sku_map = {key.upper(): value for key, value in sku_map.items()}
        for index, item in enumerate(order.get("line_items") or [], start=1):
            item_code = _mapped_line_item_code(item, variant_map, normalized_sku_map)
            if item_code is None:
                continue
            quantity = _positive_float(item.get("quantity")) or 1
            snapshot = await get_inventory(item_code, quantity)
            branch_code = _positive_int(getattr(snapshot, "admsuc_codigo", None))
            if branch_code is not None:
                line_branch_codes[index] = branch_code
        return line_branch_codes


def _records(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("data", "items", "item", "result", "results", "response", "value", "values", "records", "rows", "datos", "detalles"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                records = _records(value)
                if records:
                    return records
        list_values = [value for value in data.values() if isinstance(value, list)]
        if len(list_values) == 1:
            return [item for item in list_values[0] if isinstance(item, dict)]
        return [data] if _looks_like_record(data) else []
    return []


def _error_message(exc: Exception) -> str:
    message = str(exc).strip()
    return message or f"{type(exc).__name__}: {exc!r}"


def _first_value(record: dict[str, Any] | None, *keys: str) -> Any:
    if not record:
        return None
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def _first_int(record: dict[str, Any] | None, *keys: str) -> int | None:
    value = _first_value(record, *keys)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _shopify_tags(order: dict[str, Any]) -> list[str]:
    tags = order.get("tags")
    if isinstance(tags, str):
        values = tags.split(",")
    elif isinstance(tags, list):
        values = tags
    else:
        values = []
    cleaned = []
    for value in values:
        text = _clean_text(value)
        if text:
            cleaned.append(text)
    return cleaned


def _branch_name(branch: dict[str, Any], branch_code: int) -> str:
    return str(
        _first_value(
            branch,
            "admsuc_nombre",
            "admsuc_Nombre",
            "nombre",
            "name",
            "descripcion",
            "description",
        )
        or f"Sucursal {branch_code}"
    ).strip()[:255]


def _shopify_location_payload(branch: dict[str, Any], branch_name: str) -> dict[str, Any]:
    address = {
        "address1": _clean_text(
            _first_value(
                branch,
                "admsuc_direccion",
                "admsuc_Direccion",
                "direccion",
                "address1",
                "address",
            )
        ),
        "address2": _clean_text(_first_value(branch, "address2", "direccion2")),
        "city": _clean_text(_first_value(branch, "admsuc_ciudad", "ciudad", "city")),
        "zip": _clean_text(_first_value(branch, "admsuc_zip", "zip", "postal_code", "codigo_postal")),
        "provinceCode": _clean_text(_first_value(branch, "provinceCode", "province_code", "estado_codigo")),
        "countryCode": _shopify_country_code(_first_value(branch, "countryCode", "country_code", "pais_codigo")),
    }
    return {
        "name": branch_name,
        "address": {key: value for key, value in address.items() if value not in (None, "")},
        "fulfillsOnlineOrders": bool(
            _first_value(branch, "fulfillsOnlineOrders", "fulfills_online_orders", "cumple_online") in (None, True, 1, "1", "A")
        ),
    }


def _shopify_country_code(value: Any) -> str:
    country_code = str(value or "").strip().upper()
    return country_code if len(country_code) == 2 else "DO"


def _product_sku(product: dict[str, Any], item_code: int) -> str:
    return str(_first_value(product, "invitm_refer", "invitm_Refer", "sku", "referencia") or item_code).strip()


def _product_title(product: dict[str, Any], fallback: str) -> str:
    return str(
        _first_value(product, "invitm_nombre", "invitm_Nombre", "title", "nombre", "descripcion")
        or fallback
    ).strip()[:255]


def _product_price(product: dict[str, Any]) -> Any:
    return _first_value(product, "facpre_Contado", "facpre_contado", "precio", "price")


def _principal_prices_by_item(prices: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    by_item: dict[int, dict[str, Any]] = {}
    for price in prices:
        item_code = _first_int(price, "invitm_Codigo", "invitm_codigo", "invitmCodigo")
        amount = _first_value(price, "facpre_Contado", "facpre_contado")
        if item_code is None or amount is None:
            continue
        current = by_item.get(item_code)
        if current is None or _is_principal_price(price):
            by_item[item_code] = price
    return by_item


def _is_principal_price(price: dict[str, Any]) -> bool:
    return _first_value(price, "facpre_Principal", "facpre_principal") in (True, 1, "1")


def _prices_equal(left: Any, right: Any) -> bool:
    try:
        return round(float(left), 4) == round(float(right), 4)
    except (TypeError, ValueError):
        return str(left or "").strip() == str(right or "").strip()


def _shopify_price(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _shopify_product_payload(product: dict[str, Any]) -> dict[str, Any]:
    item_code = _first_int(product, "invitm_codigo", "invitm_Codigo", "invitmCodigo", "codigo") or 0
    sku = _product_sku(product, item_code)
    title = _product_title(product, sku)
    price = _product_price(product)
    family_name = _clean_text(_first_value(product, "invfam_nombre", "familia_nombre", "product_type"))
    brand_name = _clean_text(_first_value(product, "invmar_nombre", "marca_nombre", "vendor"))
    tags = [f"se-item:{item_code}"]
    if family_name:
        tags.append(family_name)
    if brand_name:
        tags.append(brand_name)
    variant: dict[str, Any] = {
        "sku": sku,
        "inventory_management": "shopify",
        "inventory_policy": "deny",
    }
    if price is not None:
        variant["price"] = str(price)
    payload: dict[str, Any] = {
        "title": title,
        "vendor": brand_name or "SE",
        "product_type": family_name,
        "tags": ", ".join(tags),
        "status": "active" if _first_value(product, "admsts_codigo", "active", "activo") in (None, True, 1, "1", "A") else "draft",
        "variants": [variant],
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [])}


def _first_variant(product: dict[str, Any]) -> dict[str, Any]:
    variants = product.get("variants")
    if isinstance(variants, list) and variants and isinstance(variants[0], dict):
        return variants[0]
    return {}


def _stock_quantity(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _se_customer_to_shopify(customer: dict[str, Any]) -> dict[str, Any]:
    contact_name = str(_first_value(customer, "cxccon_Nombre", "cxccon_nombre") or "").strip()
    legal_name = str(_first_value(customer, "cxccte_Nombre", "cxccte_nombre") or contact_name or "").strip()
    first_name, last_name = _split_name(contact_name or legal_name)
    customer_code = _first_int(customer, "cxccte_Codigo", "cxccte_codigo", "codigo")
    rnc = _first_value(customer, "cxccte_Rnc", "cxccte_rnc")
    phone = _normalize_phone(_first_value(customer, "cxccte_telef1", "cxccte_Telef1", "telefono", "phone"))
    payload: dict[str, Any] = {
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "note": f"SE cxccte_codigo={customer_code}; RNC={rnc or ''}".strip(),
        "tags": ", ".join(
            tag for tag in ["se-customer", f"cxccte:{customer_code}" if customer_code else "", f"rnc:{rnc}" if rnc else ""] if tag
        ),
        "addresses": [_se_customer_address(customer, legal_name)],
        "metafields": [
            {
                "namespace": "se_data",
                "key": "cxccte_codigo",
                "value": str(customer_code),
                "type": "single_line_text_field",
            },
        ],
    }
    email = _se_customer_email(customer)
    if email:
        payload["email"] = email
    return {key: value for key, value in payload.items() if value not in (None, "", [])}


def _se_customer_address(customer: dict[str, Any], legal_name: str) -> dict[str, Any]:
    first_name, last_name = _split_name(str(_first_value(customer, "cxccon_Nombre", "cxccon_nombre") or legal_name))
    address = {
        "first_name": first_name,
        "last_name": last_name,
        "company": legal_name,
        "address1": _first_value(customer, "cxcdir_Nombre", "cxcdir_nombre"),
        "phone": _normalize_phone(_first_value(customer, "cxccte_telef1", "cxccte_Telef1", "telefono", "phone")),
        "country": "Dominican Republic",
        "country_code": "DO",
        "default": True,
    }
    return {key: value for key, value in address.items() if value not in (None, "")}


def _se_customer_email(customer: dict[str, Any]) -> str | None:
    value = _first_value(customer, "email", "cxccte_Email", "cxccte_email")
    if value and "@" in str(value):
        return str(value).strip()
    refer = _first_value(customer, "cxccte_Refer", "cxccte_refer")
    if refer and "@" in str(refer):
        return str(refer).strip()
    return None


def _split_name(value: str) -> tuple[str, str]:
    parts = [part for part in value.strip().split() if part]
    if not parts:
        return "SE", "Customer"
    if len(parts) == 1:
        return parts[0][:255], "Customer"
    return parts[0][:255], " ".join(parts[1:])[:255]


def _normalize_phone(value: Any) -> str | None:
    if value in (None, ""):
        return None
    digits = "".join(character for character in str(value) if character.isdigit())
    if len(digits) == 10 and digits[0] in {"8", "9"}:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}" if digits else None


def _positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _positive_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _mapped_line_item_code(
    item: dict[str, Any],
    variant_map: dict[int, int],
    sku_map: dict[str, int],
) -> int | None:
    variant_id = _positive_int(item.get("variant_id"))
    if variant_id is not None and variant_id in variant_map:
        return variant_map[variant_id]
    sku = str(item.get("sku") or "").strip()
    if sku:
        return sku_map.get(sku.upper())
    return None


def _invoice_visit_rows(payload: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    return _company_rows(payload, "mfactrx_rows")


def _invoice_rows(payload: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    return _company_rows(payload, "mfactrx_rows")


def _company_rows(payload: list[dict[str, Any]] | dict[str, Any], wrapper_key: str | None = None) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and wrapper_key and isinstance(payload.get(wrapper_key), list):
        payload = payload[wrapper_key]
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []
    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        if row.get("admcia_codigo") in (None, "", 0, "0"):
            row["admcia_codigo"] = settings.se_company_code
        rows.append(row)
    return rows


def _fulfillment_inventory_payload(payload: dict[str, Any]) -> dict[str, Any]:
    adjustments = []
    for item in payload.get("line_items") or []:
        adjustments.append(
            {
                "invitm_codigo": _first_int(item, "invitm_codigo", "sku"),
                "cantidad": _stock_quantity(item.get("quantity")),
                "referencia": str(payload.get("id") or payload.get("order_id") or ""),
                "shopify_line_item_id": item.get("id"),
            }
        )
    return {
        "shopify_order_id": payload.get("order_id") or payload.get("shopify_order_id"),
        "shopify_fulfillment_id": payload.get("id"),
        "ajustes": [item for item in adjustments if item.get("invitm_codigo") is not None],
    }


def _outbox_event_response(event: Any) -> dict[str, Any]:
    return {
        "id": event.id,
        "target": event.target,
        "operation": event.operation,
        "status": event.status,
        "retry_count": event.retry_count,
        "next_retry_at": event.next_retry_at,
        "payload": event.payload,
    }


def _looks_like_record(record: dict[str, Any]) -> bool:
    for key in record:
        normalized = key.lower()
        if "_" in normalized or normalized.endswith(("codigo", "code", "id")):
            return True
    return False
