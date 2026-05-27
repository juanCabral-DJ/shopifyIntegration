import pytest

from app.application.services.middleware_service import MiddlewareService


class FakeIntegrationRepo:
    def __init__(self):
        self.branch_maps = []
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

    async def upsert_branch_map(self, admsuc_codigo, shopify_location_id=None, name=None, active=True):
        mapping = {
            "admsuc_codigo": admsuc_codigo,
            "shopify_location_id": shopify_location_id,
            "name": name,
            "active": active,
        }
        self.branch_maps.append(mapping)
        return mapping


class FakeSEClient:
    async def list_branches(self):
        return [
            {
                "admsuc_codigo": 1,
                "admsuc_nombre": "Principal",
                "admsuc_direccion": "Av. Winston Churchill",
                "admsuc_ciudad": "Santo Domingo",
            },
            {
                "admsuc_codigo": 2,
                "admsuc_nombre": "Santiago",
            },
        ]


class FakeShopifyClient:
    def __init__(self):
        self.list_locations_calls = 0
        self.created_locations = []

    async def list_locations(self):
        self.list_locations_calls += 1
        return [{"id": 111, "name": "Principal"}]

    async def create_location(self, location):
        created = {
            "legacyResourceId": 222,
            "name": location["name"],
            "sync_status": "created",
        }
        self.created_locations.append(location)
        return created


@pytest.mark.asyncio
async def test_sync_branches_creates_missing_shopify_locations_and_saves_mapping():
    repo = FakeIntegrationRepo()
    shopify_client = FakeShopifyClient()
    service = MiddlewareService(
        integration_repo=repo,
        se_client=FakeSEClient(),
        shopify_client=shopify_client,
    )

    result = await service.sync_branches()

    assert result == {
        "status": "success",
        "received": 2,
        "mapped": 2,
        "shopify_locations_created": 1,
        "shopify_locations_existing": 1,
    }
    assert shopify_client.list_locations_calls == 1
    assert shopify_client.created_locations == [
        {
            "name": "Santiago",
            "address": {"countryCode": "DO"},
            "fulfillsOnlineOrders": True,
        }
    ]
    assert repo.branch_maps == [
        {
            "admsuc_codigo": 1,
            "shopify_location_id": 111,
            "name": "Principal",
            "active": True,
        },
        {
            "admsuc_codigo": 2,
            "shopify_location_id": 222,
            "name": "Santiago",
            "active": True,
        },
    ]
