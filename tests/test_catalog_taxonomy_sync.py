import pytest

from app.application.services.middleware_service import MiddlewareService


class FakeIntegrationRepo:
    def __init__(self):
        self.family_maps = []
        self.brand_maps = []
        self.finished = None

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

    async def upsert_family_map(self, se_familia_id, se_familia_nombre=None, shopify_collection_id=None):
        self.family_maps.append(
            {
                "se_familia_id": se_familia_id,
                "se_familia_nombre": se_familia_nombre,
                "shopify_collection_id": shopify_collection_id,
            }
        )

    async def upsert_brand_map(self, se_marca_id, se_marca_nombre=None, shopify_tag=None):
        self.brand_maps.append(
            {
                "se_marca_id": se_marca_id,
                "se_marca_nombre": se_marca_nombre,
                "shopify_tag": shopify_tag,
            }
        )


class FakeSEClient:
    async def list_families(self):
        return [{"invfam_codigo": "10", "invfam_nombre": "Bebidas"}]

    async def list_brands(self):
        return [{"invmar_codigo": "20", "invmar_nombre": "Acme"}]


class FakeShopifyClient:
    async def ensure_custom_collection(self, title):
        assert title == "Bebidas"
        return {"id": 123, "title": title, "sync_status": "created"}


@pytest.mark.asyncio
async def test_sync_catalog_taxonomy_creates_shopify_collections_and_saves_mapping():
    repo = FakeIntegrationRepo()
    service = MiddlewareService(
        integration_repo=repo,
        se_client=FakeSEClient(),
        shopify_client=FakeShopifyClient(),
    )

    result = await service.sync_catalog_taxonomy()

    assert result == {
        "status": "success",
        "families": 1,
        "brands": 1,
        "collections_created": 1,
        "collections_existing": 0,
    }
    assert repo.family_maps == [
        {
            "se_familia_id": "10",
            "se_familia_nombre": "Bebidas",
            "shopify_collection_id": 123,
        }
    ]
    assert repo.brand_maps == [
        {
            "se_marca_id": "20",
            "se_marca_nombre": "Acme",
            "shopify_tag": "Acme",
        }
    ]
    assert repo.finished["status"] == "success"
