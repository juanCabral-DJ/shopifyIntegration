import pytest

from app.application.services.inventory_service import InventoryService


class FakeInventoryRepo:
    def __init__(self):
        self.items = {}
        self.next_id = 1

    async def list_all(self):
        return list(self.items.values())

    async def get_by_inventory_item_and_location(self, inventory_item_id, location_id):
        return self.items.get((inventory_item_id, location_id))

    async def list_by_inventory_item_id(self, inventory_item_id):
        return [
            item
            for (item_id, _location_id), item in self.items.items()
            if item_id == inventory_item_id
        ]

    async def add(self, inventory_item):
        inventory_item.id = self.next_id
        self.next_id += 1
        self.items[(inventory_item.inventory_item_id, inventory_item.location_id)] = inventory_item
        return inventory_item

    async def save(self, inventory_item):
        self.items[(inventory_item.inventory_item_id, inventory_item.location_id)] = inventory_item
        return inventory_item


class FakeShopifyClient:
    async def list_products(self):
        return [
            {
                "id": 100,
                "title": "T-Shirt",
                "variants": [
                    {
                        "id": 200,
                        "title": "Small",
                        "sku": "TS-S",
                        "inventory_item_id": 300,
                        "inventory_management": "shopify",
                    }
                ],
            }
        ]

    async def list_inventory_levels(self, inventory_item_ids):
        return [
            {
                "inventory_item_id": 300,
                "location_id": 400,
                "available": 7,
                "updated_at": "2026-04-29T12:00:00-06:00",
            }
        ]


@pytest.mark.asyncio
async def test_sync_from_shopify_creates_and_updates_inventory() -> None:
    repo = FakeInventoryRepo()
    service = InventoryService(inventory_repo=repo, shopify_client=FakeShopifyClient())

    first_result = await service.sync_from_shopify()
    second_result = await service.sync_from_shopify()

    item = repo.items[(300, 400)]
    assert first_result == {"synced": 1, "created": 1, "updated": 0}
    assert second_result == {"synced": 1, "created": 0, "updated": 1}
    assert item.shopify_product_id == 100
    assert item.shopify_variant_id == 200
    assert item.sku == "TS-S"
    assert item.available == 7
    assert item.tracked is True


@pytest.mark.asyncio
async def test_inventory_level_webhook_updates_existing_inventory() -> None:
    repo = FakeInventoryRepo()
    service = InventoryService(inventory_repo=repo, shopify_client=FakeShopifyClient())
    await service.sync_from_shopify()

    await service.handle_inventory_level_update(
        {
            "inventory_item_id": 300,
            "location_id": 400,
            "available": 3,
            "updated_at": "2026-04-29T12:30:00-06:00",
        }
    )

    assert repo.items[(300, 400)].available == 3
