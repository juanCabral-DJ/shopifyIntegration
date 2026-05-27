from datetime import datetime
from typing import Any

from app.domain.models.inventory_item import InventoryItem
from app.infrastructure.repositories.inventory_repository import InventoryRepository
from app.infrastructure.shopify.client import ShopifyClient


class InventoryService:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        shopify_client: ShopifyClient | None = None,
    ) -> None:
        self.inventory_repo = inventory_repo
        self.shopify_client = shopify_client

    async def list_inventory(self) -> list[InventoryItem]:
        return await self.inventory_repo.list_all()

    async def sync_from_shopify(self) -> dict[str, int]:
        if not self.shopify_client:
            raise ValueError("Shopify client is required to sync inventory")

        products = await self.shopify_client.list_products()
        variant_index = self._build_variant_index(products)
        levels = await self.shopify_client.list_inventory_levels(list(variant_index.keys()))
        created = 0
        updated = 0

        for level in levels:
            variant = variant_index.get(int(level["inventory_item_id"]))
            if not variant:
                continue
            existing = await self.upsert_inventory_level(level, variant)
            if existing:
                updated += 1
            else:
                created += 1

        return {
            "synced": created + updated,
            "created": created,
            "updated": updated,
        }

    async def handle_inventory_level_update(self, payload: dict[str, Any]) -> None:
        inventory_item_id = payload.get("inventory_item_id")
        location_id = payload.get("location_id")
        if not inventory_item_id or not location_id:
            return

        items = await self.inventory_repo.list_by_inventory_item_id(int(inventory_item_id))
        existing = await self.inventory_repo.get_by_inventory_item_and_location(
            int(inventory_item_id),
            int(location_id),
        )
        template = existing or (items[0] if items else None)
        if not template:
            return

        await self.upsert_inventory_level(
            payload,
            {
                "shopify_product_id": template.shopify_product_id,
                "shopify_variant_id": template.shopify_variant_id,
                "sku": template.sku,
                "product_title": template.product_title,
                "variant_title": template.variant_title,
                "tracked": template.tracked,
            },
        )

    async def handle_inventory_item_update(self, payload: dict[str, Any]) -> None:
        inventory_item_id = payload.get("id")
        if not inventory_item_id:
            return

        items = await self.inventory_repo.list_by_inventory_item_id(int(inventory_item_id))
        for item in items:
            item.sku = payload.get("sku", item.sku)
            item.tracked = bool(payload.get("tracked", item.tracked))
            item.shopify_updated_at = self._parse_datetime(payload.get("updated_at")) or item.shopify_updated_at
            await self.inventory_repo.save(item)

    async def handle_product_update(self, payload: dict[str, Any]) -> None:
        if not self.shopify_client:
            return

        variant_index = self._build_variant_index([payload])
        levels = await self.shopify_client.list_inventory_levels(list(variant_index.keys()))
        for level in levels:
            variant = variant_index.get(int(level["inventory_item_id"]))
            if variant:
                await self.upsert_inventory_level(level, variant)

    async def upsert_inventory_level(
        self,
        level: dict[str, Any],
        variant: dict[str, Any],
    ) -> InventoryItem | None:
        inventory_item_id = int(level["inventory_item_id"])
        location_id = int(level["location_id"])
        existing = await self.inventory_repo.get_by_inventory_item_and_location(inventory_item_id, location_id)

        if existing is None:
            item = InventoryItem(
                shopify_product_id=int(variant["shopify_product_id"]),
                shopify_variant_id=int(variant["shopify_variant_id"]),
                inventory_item_id=inventory_item_id,
                location_id=location_id,
                sku=variant.get("sku"),
                product_title=variant.get("product_title") or "",
                variant_title=variant.get("variant_title"),
                available=level.get("available"),
                tracked=bool(variant.get("tracked", True)),
                shopify_updated_at=self._parse_datetime(level.get("updated_at")),
            )
            await self.inventory_repo.add(item)
            return None

        existing.shopify_product_id = int(variant["shopify_product_id"])
        existing.shopify_variant_id = int(variant["shopify_variant_id"])
        existing.sku = variant.get("sku")
        existing.product_title = variant.get("product_title") or existing.product_title
        existing.variant_title = variant.get("variant_title")
        existing.available = level.get("available")
        existing.tracked = bool(variant.get("tracked", existing.tracked))
        existing.shopify_updated_at = self._parse_datetime(level.get("updated_at")) or existing.shopify_updated_at
        await self.inventory_repo.save(existing)
        return existing

    def _build_variant_index(self, products: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        variants = {}
        for product in products:
            for variant in product.get("variants", []):
                inventory_item_id = variant.get("inventory_item_id")
                if not inventory_item_id:
                    continue
                variants[int(inventory_item_id)] = {
                    "shopify_product_id": int(product["id"]),
                    "shopify_variant_id": int(variant["id"]),
                    "sku": variant.get("sku"),
                    "product_title": product.get("title", ""),
                    "variant_title": variant.get("title"),
                    "tracked": variant.get("inventory_management") is not None,
                }
        return variants

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
