from typing import Any
from decimal import Decimal, InvalidOperation

import httpx

from app.application.normalization import (
    clean_text,
    error_message,
    first_int,
    first_value,
    first_variant,
    positive_int,
    product_price,
    product_sku,
    records,
)
from app.application.ports import ExternalCatalogPort, IntegrationMappingPort, ShopifyCatalogPort
from app.application.transformers.se_to_shopify import shopify_product_payload
from app.infrastructure.se.client import ExternalSystemNotConfigured


class ProductSyncService:
    def __init__(
        self,
        integration_repo: IntegrationMappingPort,
        shopify_client: ShopifyCatalogPort,
        external_client: ExternalCatalogPort,
    ) -> None:
        self.integration_repo = integration_repo
        self.shopify_client = shopify_client
        self.external_client = external_client

    async def sync_products(self, payload: Any = None, run: Any | None = None) -> dict[str, Any]:
        run = run or await self.integration_repo.start_sync_run("products")
        try:
            products = records(await self.external_client.list_products(payload))
            item_codes = [
                item_code
                for product in products
                if (item_code := first_int(product, "invitm_codigo", "invitm_Codigo", "invitmCodigo", "codigo")) is not None
            ]
            existing_mappings = await self._existing_mappings_by_item_code(item_codes)
            mapped = 0
            created = 0
            updated = 0
            skipped = 0
            shopify_skipped = 0
            priced = 0
            shopify_variant_index: dict[str, tuple[dict[str, Any], dict[str, Any]]] | None = None

            for processed, product in enumerate(products, start=1):
                item_code = first_int(product, "invitm_codigo", "invitm_Codigo", "invitmCodigo", "codigo")
                if item_code is None:
                    skipped += 1
                    continue

                sku = product_sku(product, item_code)
                if product_price(product) is not None:
                    priced += 1
                existing = existing_mappings.get(item_code)
                if _can_skip_shopify_update(product, existing):
                    variant = {
                        "id": _mapping_value(existing, "shopify_variant_id"),
                        "inventory_item_id": _mapping_value(existing, "shopify_inventory_item_id"),
                    }
                    await self.integration_repo.upsert_sku_map(
                        invitm_codigo=item_code,
                        sku=sku,
                        shopify_product_id=positive_int(_mapping_value(existing, "shopify_product_id")),
                        shopify_variant_id=positive_int(_mapping_value(existing, "shopify_variant_id")),
                        shopify_inventory_item_id=positive_int(_mapping_value(existing, "shopify_inventory_item_id")),
                        last_price=product_price(product),
                        active=_product_active(product),
                        existing_mapping=existing,
                    )
                    await self._ensure_product_collection(product, {"id": _mapping_value(existing, "shopify_product_id"), "variants": [variant]})
                    mapped += 1
                    shopify_skipped += 1
                    if processed % 100 == 0:
                        await self.integration_repo.update_sync_run_stats(
                            run,
                            {
                                "received": len(products),
                                "processed": processed,
                                "mapped": mapped,
                                "shopify_created": created,
                                "shopify_updated": updated,
                                "shopify_skipped": shopify_skipped,
                                "skipped": skipped,
                                "priced": priced,
                            },
                        )
                        session = getattr(self.integration_repo, "session", None)
                        if session is not None:
                            await session.commit()
                    continue
                if existing is None and shopify_variant_index is None:
                    shopify_variant_index = await self._shopify_variant_index()

                shopify_product = await self._upsert_shopify_product(product, existing, shopify_variant_index)
                if shopify_product.get("sync_status") == "created":
                    created += 1
                else:
                    updated += 1

                variant = first_variant(shopify_product)
                if shopify_variant_index is not None:
                    normalized_sku = sku.strip().casefold()
                    if normalized_sku and variant:
                        shopify_variant_index[normalized_sku] = (shopify_product, variant)

                await self.integration_repo.upsert_sku_map(
                    invitm_codigo=item_code,
                    sku=sku,
                    shopify_product_id=first_int(shopify_product, "id"),
                    shopify_variant_id=first_int(variant, "id"),
                    shopify_inventory_item_id=first_int(variant, "inventory_item_id"),
                    last_price=product_price(product),
                    active=_product_active(product),
                    existing_mapping=existing,
                )
                await self._ensure_product_collection(product, shopify_product)
                mapped += 1

                if processed % 100 == 0:
                    await self.integration_repo.update_sync_run_stats(
                        run,
                        {
                            "received": len(products),
                            "processed": processed,
                            "mapped": mapped,
                            "shopify_created": created,
                            "shopify_updated": updated,
                            "shopify_skipped": shopify_skipped,
                            "skipped": skipped,
                            "priced": priced,
                        },
                    )
                    session = getattr(self.integration_repo, "session", None)
                    if session is not None:
                        await session.commit()

            stats = {
                "received": len(products),
                "mapped": mapped,
                "shopify_created": created,
                "shopify_updated": updated,
                "shopify_skipped": shopify_skipped,
                "skipped": skipped,
                "priced": priced,
            }
            await self.integration_repo.add_outbox_event(
                target="shopify",
                operation="products.sync",
                payload={"source": "se", "created": created, "updated": updated, **stats},
                status="done",
            )
            await self.integration_repo.finish_sync_run(run, "success", stats)
            return {"status": "success", **stats}
        except (ExternalSystemNotConfigured, httpx.HTTPError, ValueError) as exc:
            message = error_message(exc)
            await self.integration_repo.finish_sync_run(run, "failed", error_message=message)
            return {"status": "failed", "error": message}

    async def _existing_mappings_by_item_code(self, item_codes: list[int]) -> dict[int, Any]:
        if hasattr(self.integration_repo, "get_sku_maps_by_item_codes"):
            return await self.integration_repo.get_sku_maps_by_item_codes(item_codes)

        mappings = {}
        for item_code in item_codes:
            mapping = await self.integration_repo.get_sku_map_by_item_code(item_code)
            if mapping is not None:
                mappings[item_code] = mapping
        return mappings

    async def _upsert_shopify_product(
        self,
        product: dict[str, Any],
        existing_mapping: Any | None = None,
        shopify_variant_index: dict[str, tuple[dict[str, Any], dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        item_code = first_int(product, "invitm_codigo", "invitm_Codigo", "invitmCodigo", "codigo")
        if item_code is None:
            raise ValueError("Product item code is required")

        sku = product_sku(product, item_code)
        payload = shopify_product_payload(product)
        product_id = positive_int(getattr(existing_mapping, "shopify_product_id", None))
        variant_id = positive_int(getattr(existing_mapping, "shopify_variant_id", None))

        if product_id is None:
            found = (
                shopify_variant_index.get(sku.strip().casefold())
                if shopify_variant_index is not None
                else await self.shopify_client.find_product_variant_by_sku(sku)
            )
            if found:
                found_product, variant = found
                product_id = first_int(found_product, "id")
                variant_id = first_int(variant, "id")

        if product_id is not None:
            if variant_id is not None and payload.get("variants"):
                payload["variants"][0]["id"] = variant_id
            updated = await self.shopify_client.update_product(product_id, payload)
            updated["sync_status"] = "updated"
            return updated

        created = await self.shopify_client.create_product(payload)
        created["sync_status"] = "created"
        return created

    async def _shopify_variant_index(self) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
        index: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        for product in await self.shopify_client.list_products():
            for variant in product.get("variants") or []:
                sku = str(variant.get("sku") or "").strip().casefold()
                if sku and sku not in index:
                    index[sku] = (product, variant)
        return index

    async def _ensure_product_collection(self, product: dict[str, Any], shopify_product: dict[str, Any]) -> None:
        family_name = clean_text(first_value(product, "invfam_nombre", "familia_nombre", "product_type"))
        product_id = first_int(shopify_product, "id")
        if not family_name or product_id is None:
            return
        family_map = await self.integration_repo.get_family_map_by_name(family_name)
        collection_id = positive_int(getattr(family_map, "shopify_collection_id", None)) if family_map else None
        if collection_id is not None:
            await self.shopify_client.ensure_collect(product_id, collection_id)


def _mapping_value(mapping: Any | None, key: str) -> Any:
    if mapping is None:
        return None
    if isinstance(mapping, dict):
        return mapping.get(key)
    return getattr(mapping, key, None)


def _product_active(product: dict[str, Any]) -> bool:
    return bool(first_value(product, "activo", "active", "admsts_codigo") in (None, True, 1, "1", "A"))


def _decimal_equal(left: Any, right: Any) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, ValueError):
        return str(left) == str(right)


def _can_skip_shopify_update(product: dict[str, Any], existing_mapping: Any | None) -> bool:
    if existing_mapping is None:
        return False
    if positive_int(_mapping_value(existing_mapping, "shopify_product_id")) is None:
        return False
    if positive_int(_mapping_value(existing_mapping, "shopify_variant_id")) is None:
        return False
    if positive_int(_mapping_value(existing_mapping, "shopify_inventory_item_id")) is None:
        return False
    if not _decimal_equal(_mapping_value(existing_mapping, "last_price"), product_price(product)):
        return False
    return bool(_mapping_value(existing_mapping, "active")) == _product_active(product)
