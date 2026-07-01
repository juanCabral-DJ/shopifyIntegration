from typing import Any
import httpx
import logging
from decimal import Decimal

from app.application.normalization import (
    records,
    first_value,
    first_int,
    positive_int,
    first_variant,
    product_sku,
    product_price,
    stock_quantity,
    shopify_product_payload,
    error_message,
)
from app.application.ports import ExternalCatalogPort, IntegrationMappingPort, ShopifyCatalogPort
from app.core.config import settings
from app.infrastructure.se.client import ExternalSystemNotConfigured

logger = logging.getLogger(__name__)


class InventorySyncService:
    def __init__(
        self,
        integration_repo: IntegrationMappingPort,
        shopify_client: ShopifyCatalogPort,
        external_client: ExternalCatalogPort,
    ) -> None:
        self.integration_repo = integration_repo
        self.shopify_client = shopify_client
        self.external_client = external_client

    async def sync_inventory(
        self,
        payload: Any = None,
        reconcile: bool = False,
        run: Any | None = None,
    ) -> dict[str, Any]:
        run = run or await self.integration_repo.start_sync_run("inventory_reconcile" if reconcile else "inventory")
        try:
            products = await self.external_client.list_products(payload)
            product_records = records(products)
            physical = await self.external_client.list_physical_inventory() if reconcile else []
            physical_records = records(physical)
            physical_by_item = {
                item_code: record
                for record in physical_records
                if (item_code := first_int(record, "invitm_codigo", "invitm_Codigo", "codigo")) is not None
            }
            snapshots = 0
            inventory_updated = 0
            inventory_skipped = 0
            discrepancies = 0
            location_id = await self._default_shopify_location_id()
            for processed, product in enumerate(product_records, start=1):
                item_code = first_int(product, "invitm_codigo", "invitm_Codigo", "codigo")
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

                stock = first_value(product, "invcos_Exist", "invcos_exist", "se_stock", "stock", "existencia", "invitm_existencia") or 0
                physical_record = physical_by_item.get(item_code)
                mapping = await self.integration_repo.get_sku_map_by_item_code(item_code)
                if mapping is None or not mapping.shopify_inventory_item_id:
                    shopify_product = await self._upsert_shopify_product(product, mapping)
                    variant = first_variant(shopify_product)
                    mapping = await self.integration_repo.upsert_sku_map(
                        invitm_codigo=item_code,
                        sku=product_sku(product, item_code),
                        shopify_product_id=first_int(shopify_product, "id"),
                        shopify_variant_id=first_int(variant, "id"),
                        shopify_inventory_item_id=first_int(variant, "inventory_item_id"),
                        last_price=product_price(product),
                        active=bool(first_value(product, "activo", "active", "admsts_codigo") in (None, True, 1, "1", "A")),
                    )
                if mapping.shopify_inventory_item_id and location_id is not None:
                    final_stock = stock_quantity(stock)
                    await self.shopify_client.set_inventory_level(
                        int(mapping.shopify_inventory_item_id),
                        location_id,
                        final_stock,
                    )
                    inventory_updated += 1
                else:
                    inventory_skipped += 1
                mobile_stock = (
                    first_value(physical_record, "cantidad_fisica", "cantidad", "stock")
                    if physical_record
                    else None
                )
                if reconcile and mobile_stock is not None:
                    difference = abs(stock_quantity(mobile_stock) - stock_quantity(stock))
                    if difference > settings.inventory_discrepancy_threshold:
                        discrepancies += 1
                        await self.integration_repo.add_outbox_event(
                            target="internal",
                            operation="alert.inventory_discrepancy",
                            payload={
                                "invitm_codigo": item_code,
                                "se_stock": stock_quantity(stock),
                                "mobile_physical_stock": stock_quantity(mobile_stock),
                                "difference": difference,
                            },
                        )
                await self.integration_repo.add_inventory_snapshot(
                    invitm_codigo=item_code,
                    se_stock=stock,
                    admsuc_codigo=first_int(product, "admsuc_codigo", "admsuc_Codigo"),
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
            message = error_message(exc)
            logger.exception("Inventory sync failed")
            await self.integration_repo.finish_sync_run(run, "failed", error_message=message)
            return {"status": "failed", "error": message}

    async def _default_shopify_location_id(self) -> int | None:
        if hasattr(self.integration_repo, "get_first_branch_map_with_location"):
            branch = await self.integration_repo.get_first_branch_map_with_location()
            if branch and branch.shopify_location_id:
                return int(branch.shopify_location_id)
        locations = await self.shopify_client.list_locations()
        for location in locations:
            if location.get("active", True) and location.get("id") is not None:
                return int(location["id"])
        return None

    async def _upsert_shopify_product(
        self,
        product: dict[str, Any],
        existing_mapping: Any | None = None,
    ) -> dict[str, Any]:
        item_code = first_int(product, "invitm_codigo", "invitm_Codigo", "invitmCodigo", "codigo")
        if item_code is None:
            raise ValueError("Product item code is required")
        sku = product_sku(product, item_code)
        payload = shopify_product_payload(product)
        product_id = positive_int(getattr(existing_mapping, "shopify_product_id", None))
        variant_id = positive_int(getattr(existing_mapping, "shopify_variant_id", None))

        if product_id is None:
            found = await self.shopify_client.find_product_variant_by_sku(sku)
            if found:
                found_product, _variant = found
                product_id = first_int(found_product, "id")
                variant_id = first_int(_variant, "id")

        if product_id is not None:
            if variant_id is not None and payload.get("variants"):
                payload["variants"][0]["id"] = variant_id
            updated = await self.shopify_client.update_product(product_id, payload)
            updated["sync_status"] = "updated"
            return updated

        created = await self.shopify_client.create_product(payload)
        created["sync_status"] = "created"
        return created

    async def _update_inventory_sync_progress(
        self,
        run: Any,
        processed: int,
        products_total: int,
        physical_total: int,
        snapshots: int,
        updated: int,
        skipped: int,
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
                "products_received": products_total,
                "physical_counts_received": physical_total,
                "processed": processed,
                "snapshots": snapshots,
                "shopify_inventory_updated": updated,
                "shopify_inventory_skipped": skipped,
                "discrepancies": discrepancies,
                "reconcile": reconcile,
            },
        )
        session = getattr(self.integration_repo, "session", None)
        if session is not None:
            await session.commit()
