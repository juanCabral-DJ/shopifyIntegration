import pytest
from app.application.services.middleware_service import MiddlewareService


class FakeIntegrationRepo:
    def __init__(self):
        self.sku_maps = {}
        self.outbox_events = []
        self.finished = None
        self.bulk_mapping_calls = 0

    async def start_sync_run(self, sync_type):
        return {"sync_type": sync_type}

    async def finish_sync_run(self, run, status, stats=None, error_message=None):
        self.finished = {
            "run": run,
            "status": status,
            "stats": stats,
            "error_message": error_message,
        }
        return self.finished

    async def update_sync_run_stats(self, run, stats):
        return {"run": run, "stats": stats}

    async def get_sku_map_by_item_code(self, invitm_codigo):
        return self.sku_maps.get(invitm_codigo)

    async def get_sku_maps_by_item_codes(self, invitm_codigos):
        self.bulk_mapping_calls += 1
        return {
            item_code: self.sku_maps[item_code]
            for item_code in invitm_codigos
            if item_code in self.sku_maps
        }

    async def upsert_sku_map(
        self,
        invitm_codigo,
        sku,
        shopify_product_id=None,
        shopify_variant_id=None,
        shopify_inventory_item_id=None,
        last_price=None,
        active=True,
        existing_mapping=None,
    ):
        mapping = {
            "invitm_codigo": invitm_codigo,
            "sku": sku,
            "shopify_product_id": shopify_product_id,
            "shopify_variant_id": shopify_variant_id,
            "shopify_inventory_item_id": shopify_inventory_item_id,
            "last_price": last_price,
            "active": active,
        }
        self.sku_maps[invitm_codigo] = mapping
        return mapping

    async def get_family_map_by_name(self, se_familia_nombre):
        return None

    async def add_outbox_event(self, target, operation, payload, status="pending"):
        event = {
            "target": target,
            "operation": operation,
            "payload": payload,
            "status": status,
        }
        self.outbox_events.append(event)
        return event


class FakeSEClient:
    async def list_products(self, payload=None):
        return [
            {"invitm_codigo": 1, "invitm_refer": "SKU-1", "invitm_nombre": "Producto 1", "facpre_Contado": 10.5},
            {"invitm_codigo": 2, "invitm_refer": "SKU-2", "invitm_nombre": "Producto 2", "facpre_Contado": 20},
        ]


class FakeShopifyClient:
    def __init__(self):
        self.list_products_calls = 0
        self.created_products = []
        self.create_payloads = []

    async def list_products(self):
        self.list_products_calls += 1
        return []

    async def create_product(self, product):
        self.create_payloads.append(product)
        product_id = 100 + len(self.created_products)
        created = {
            "id": product_id,
            "title": product["title"],
            "variants": [
                {
                    "id": 200 + len(self.created_products),
                    "sku": product["variants"][0]["sku"],
                    "inventory_item_id": 300 + len(self.created_products),
                }
            ],
        }
        self.created_products.append(created)
        return created

    async def update_product(self, product_id, product):
        raise AssertionError("mapped unchanged products should not be sent to Shopify")


@pytest.mark.asyncio
async def test_sync_products_indexes_shopify_products_once_for_missing_mappings():
    repo = FakeIntegrationRepo()
    shopify_client = FakeShopifyClient()
    service = MiddlewareService(
        integration_repo=repo,
        se_client=FakeSEClient(),
        shopify_client=shopify_client,
    )

    result = await service.sync_products()

    assert result["status"] == "success"
    assert result["received"] == 2
    assert result["mapped"] == 2
    assert shopify_client.list_products_calls == 1
    assert len(shopify_client.created_products) == 2
    assert shopify_client.create_payloads[0]["variants"][0]["price"] == "10.5"
    assert shopify_client.create_payloads[1]["variants"][0]["price"] == "20"
    assert repo.sku_maps[1]["last_price"] == 10.5
    assert repo.sku_maps[2]["last_price"] == 20
    assert repo.bulk_mapping_calls == 1


@pytest.mark.asyncio
async def test_sync_products_skips_shopify_update_for_complete_unchanged_mapping():
    repo = FakeIntegrationRepo()
    repo.sku_maps[1] = {
        "invitm_codigo": 1,
        "sku": "SKU-1",
        "shopify_product_id": 100,
        "shopify_variant_id": 200,
        "shopify_inventory_item_id": 300,
        "last_price": 10.5,
        "active": True,
    }
    shopify_client = FakeShopifyClient()
    service = MiddlewareService(
        integration_repo=repo,
        se_client=FakeSEClient(),
        shopify_client=shopify_client,
    )

    result = await service.sync_products()

    assert result["status"] == "success"
    assert result["shopify_skipped"] == 1
    assert shopify_client.list_products_calls == 1
    assert len(shopify_client.created_products) == 1
