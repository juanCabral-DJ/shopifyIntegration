import pytest
from httpx import AsyncClient
from app.infrastructure.shopify.client import ShopifyClient

@pytest.mark.asyncio
async def test_update_order_payment_builds_url(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"transaction": {"id": "txn_123"}}

    async def fake_post(self, url, json, headers, timeout, params=None):
        captured["url"] = url
        captured["json"] = json
        captured["params"] = params
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(AsyncClient, "post", fake_post)
    client = ShopifyClient(
        shop="pruebadevs.myshopify.com",
        api_version="2026-01",
        access_token="token",
    )
    result = await client.update_order_payment(123, 100.0, "USD")

    assert "transaction" in result
    assert captured["url"].endswith("/orders/123/transactions.json")
    assert captured["params"] == {"source": "external"}
    assert captured["json"]["transaction"]["kind"] == "sale"
    assert captured["json"]["transaction"]["amount"] == "100.00"
    assert captured["json"]["transaction"]["currency"] == "USD"
    assert captured["json"]["transaction"]["source"] == "external"
    assert captured["json"]["transaction"]["status"] == "success"


@pytest.mark.asyncio
async def test_list_orders_follows_pagination(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, orders, next_url=None):
            self._orders = orders
            self.links = {"next": {"url": next_url}} if next_url else {}

        def raise_for_status(self):
            pass

        def json(self):
            return {"orders": self._orders}

    async def fake_get(self, url, params, headers, timeout):
        calls.append({"url": url, "params": params})
        if len(calls) == 1:
            return FakeResponse([{"id": 1}], "https://example.myshopify.com/admin/api/2026-01/orders.json?page_info=abc")
        return FakeResponse([{"id": 2}])

    monkeypatch.setattr(AsyncClient, "get", fake_get)
    client = ShopifyClient(
        shop="example.myshopify.com",
        api_version="2026-01",
        access_token="token",
    )

    orders = await client.list_orders()

    assert orders == [{"id": 1}, {"id": 2}]
    assert calls[0]["params"] == {"status": "any", "limit": 250}
    assert calls[1]["params"] is None


@pytest.mark.asyncio
async def test_list_inventory_levels_chunks_inventory_item_ids(monkeypatch):
    calls = []

    class FakeResponse:
        links = {}

        def raise_for_status(self):
            pass

        def json(self):
            return {"inventory_levels": [{"inventory_item_id": 1, "location_id": 10, "available": 5}]}

    async def fake_get(self, url, params, headers, timeout):
        calls.append(params)
        return FakeResponse()

    monkeypatch.setattr(AsyncClient, "get", fake_get)
    client = ShopifyClient(
        shop="example.myshopify.com",
        api_version="2026-01",
        access_token="token",
    )

    levels = await client.list_inventory_levels(list(range(1, 53)))

    assert levels == [
        {"inventory_item_id": 1, "location_id": 10, "available": 5},
        {"inventory_item_id": 1, "location_id": 10, "available": 5},
    ]
    assert calls[0]["inventory_item_ids"] == ",".join(str(item_id) for item_id in range(1, 51))
    assert calls[1]["inventory_item_ids"] == "51,52"


@pytest.mark.asyncio
async def test_update_product_builds_payload(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"product": {"id": 123, "title": "Pepsi"}}

    async def fake_put(self, url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(AsyncClient, "put", fake_put)
    client = ShopifyClient(
        shop="pruebadevs.myshopify.com",
        api_version="2026-01",
        access_token="token",
    )

    product = await client.update_product(123, {"title": "Pepsi"})

    assert product["id"] == 123
    assert captured["url"].endswith("/products/123.json")
    assert captured["json"] == {"product": {"title": "Pepsi", "id": 123}}


@pytest.mark.asyncio
async def test_ensure_custom_collection_reuses_existing_collection(monkeypatch):
    post_called = False

    class FakeResponse:
        links = {}

        def raise_for_status(self):
            pass

        def json(self):
            return {"custom_collections": [{"id": 123, "title": "Bebidas"}]}

    async def fake_get(self, url, params, headers, timeout):
        assert url.endswith("/custom_collections.json")
        assert params == {"limit": 250}
        return FakeResponse()

    async def fake_post(self, url, json, headers, timeout):
        nonlocal post_called
        post_called = True
        return FakeResponse()

    monkeypatch.setattr(AsyncClient, "get", fake_get)
    monkeypatch.setattr(AsyncClient, "post", fake_post)
    client = ShopifyClient(
        shop="pruebadevs.myshopify.com",
        api_version="2026-01",
        access_token="token",
    )

    collection = await client.ensure_custom_collection(" bebidas ")

    assert collection["id"] == 123
    assert collection["sync_status"] == "exists"
    assert post_called is False


@pytest.mark.asyncio
async def test_ensure_custom_collection_creates_missing_collection(monkeypatch):
    captured = {}

    class ListResponse:
        links = {}

        def raise_for_status(self):
            pass

        def json(self):
            return {"custom_collections": []}

    class CreateResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"custom_collection": {"id": 456, "title": "Ferreteria"}}

    async def fake_get(self, url, params, headers, timeout):
        return ListResponse()

    async def fake_post(self, url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        return CreateResponse()

    monkeypatch.setattr(AsyncClient, "get", fake_get)
    monkeypatch.setattr(AsyncClient, "post", fake_post)
    client = ShopifyClient(
        shop="pruebadevs.myshopify.com",
        api_version="2026-01",
        access_token="token",
    )

    collection = await client.ensure_custom_collection("Ferreteria")

    assert collection["id"] == 456
    assert collection["sync_status"] == "created"
    assert captured["url"].endswith("/custom_collections.json")
    assert captured["json"] == {"custom_collection": {"title": "Ferreteria"}}


@pytest.mark.asyncio
async def test_create_location_uses_graphql_location_add(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": {
                    "locationAdd": {
                        "location": {
                            "id": "gid://shopify/Location/123",
                            "legacyResourceId": "123",
                            "name": "Santiago",
                            "fulfillsOnlineOrders": True,
                        },
                        "userErrors": [],
                    }
                }
            }

    async def fake_post(self, url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(AsyncClient, "post", fake_post)
    client = ShopifyClient(
        shop="pruebadevs.myshopify.com",
        api_version="2026-01",
        access_token="token",
    )

    location = await client.create_location(
        {
            "name": "Santiago",
            "address": {"countryCode": "DO"},
            "fulfillsOnlineOrders": True,
        }
    )

    assert captured["url"].endswith("/graphql.json")
    assert "locationAdd" in captured["json"]["query"]
    assert captured["json"]["variables"]["input"]["name"] == "Santiago"
    assert captured["json"]["variables"]["input"]["address"] == {"countryCode": "DO"}
    assert location["legacyResourceId"] == "123"
    assert location["sync_status"] == "created"
