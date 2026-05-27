import asyncio
import httpx
from typing import Any


def _raise_for_status(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = response.text.strip()
        if detail:
            message = f"{exc} Shopify response: {detail}"
            raise httpx.HTTPStatusError(message, request=exc.request, response=exc.response) from exc
        raise


def _raise_graphql_errors(data: dict[str, Any], mutation_name: str) -> None:
    errors = data.get("errors")
    if errors:
        raise ValueError(f"Shopify GraphQL errors: {errors}")
    user_errors = (data.get("data") or {}).get(mutation_name, {}).get("userErrors") or []
    if user_errors:
        messages = "; ".join(str(error.get("message") or error) for error in user_errors)
        raise ValueError(f"Shopify {mutation_name} errors: {messages}")


_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
_TRANSIENT_HTTP_ERRORS = (
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
    httpx.TimeoutException,
)
_REQUEST_INTERVAL_SECONDS = 0.6
_request_lock = asyncio.Lock()
_last_request_at = 0.0


async def _throttle_shopify_request() -> None:
    global _last_request_at
    async with _request_lock:
        now = asyncio.get_running_loop().time()
        wait_seconds = _REQUEST_INTERVAL_SECONDS - (now - _last_request_at)
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        _last_request_at = asyncio.get_running_loop().time()


async def _send_with_retries(send, attempts: int = 5) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            await _throttle_shopify_request()
            response = await send()
            status_code = getattr(response, "status_code", None)
            if status_code not in _TRANSIENT_STATUS_CODES:
                _raise_for_status(response)
                return response

            if attempt == attempts - 1:
                _raise_for_status(response)
                return response

            retry_after = response.headers.get("Retry-After") if hasattr(response, "headers") else None
            delay = float(retry_after) if retry_after else min(2 ** attempt, 8)
        except _TRANSIENT_HTTP_ERRORS as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise
            delay = min(2 ** attempt, 8)
        await asyncio.sleep(delay)

    if last_error:
        raise last_error
    raise RuntimeError("Shopify request failed without a response")


class ShopifyClient:
    def __init__(self, shop: str, api_version: str, access_token: str) -> None:
        self.base_url = f"https://{shop}/admin/api/{api_version}"
        self.headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token,
        }

    async def create_manual_payment_transaction(
        self,
        shopify_order_id: int,
        amount: float,
        currency: str,
        gateway: str = "manual",
    ) -> dict[str, Any]:
        url = f"{self.base_url}/orders/{shopify_order_id}/transactions.json"
        payload = {
            "transaction": {
                "kind": "sale",
                "amount": f"{amount:.2f}",
                "currency": currency,
                "source": "external",
                "status": "success",
            }
        }
        if gateway:
            payload["transaction"]["gateway"] = gateway

        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.post(
                url,
                params={"source": "external"},
                json=payload,
                headers=self.headers,
                timeout=30.0,
            )
            _raise_for_status(response)
            return response.json()

    async def update_order_payment(self, shopify_order_id: int, amount: float, currency: str) -> dict[str, Any]:
        return await self.create_manual_payment_transaction(shopify_order_id, amount, currency)

    async def list_orders(self, status: str = "any", limit: int = 250) -> list[dict[str, Any]]:
        url = f"{self.base_url}/orders.json"
        params: dict[str, Any] | None = {
            "status": status,
            "limit": min(limit, 250),
        }
        orders: list[dict[str, Any]] = []

        async with httpx.AsyncClient(trust_env=False) as client:
            while url:
                response = await client.get(url, params=params, headers=self.headers, timeout=30.0)
                _raise_for_status(response)
                orders.extend(response.json().get("orders", []))
                next_link = response.links.get("next", {})
                url = next_link.get("url")
                params = None

        return orders

    async def get_order(self, shopify_order_id: int) -> dict[str, Any]:
        url = f"{self.base_url}/orders/{shopify_order_id}.json"
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(url, headers=self.headers, timeout=30.0)
            _raise_for_status(response)
            return response.json()["order"]

    async def list_products(self, limit: int = 250) -> list[dict[str, Any]]:
        url = f"{self.base_url}/products.json"
        params: dict[str, Any] | None = {"limit": min(limit, 250)}
        products: list[dict[str, Any]] = []

        async with httpx.AsyncClient(trust_env=False) as client:
            while url:
                response = await _send_with_retries(
                    lambda: client.get(url, params=params, headers=self.headers, timeout=30.0)
                )
                products.extend(response.json().get("products", []))
                next_link = response.links.get("next", {})
                url = next_link.get("url")
                params = None

        return products

    async def create_product(self, product: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/products.json"
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await _send_with_retries(
                lambda: client.post(
                    url,
                    json={"product": product},
                    headers=self.headers,
                    timeout=30.0,
                )
            )
            return response.json()["product"]

    async def update_product(self, shopify_product_id: int, product: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/products/{shopify_product_id}.json"
        payload = dict(product)
        payload["id"] = shopify_product_id
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await _send_with_retries(
                lambda: client.put(
                    url,
                    json={"product": payload},
                    headers=self.headers,
                    timeout=30.0,
                )
            )
            return response.json()["product"]

    async def find_product_variant_by_sku(self, sku: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        normalized_sku = sku.strip().casefold()
        if not normalized_sku:
            return None
        for product in await self.list_products():
            for variant in product.get("variants") or []:
                if str(variant.get("sku") or "").strip().casefold() == normalized_sku:
                    return product, variant
        return None

    async def list_custom_collections(self, limit: int = 250) -> list[dict[str, Any]]:
        url = f"{self.base_url}/custom_collections.json"
        params: dict[str, Any] | None = {"limit": min(limit, 250)}
        collections: list[dict[str, Any]] = []

        async with httpx.AsyncClient(trust_env=False) as client:
            while url:
                response = await client.get(url, params=params, headers=self.headers, timeout=30.0)
                _raise_for_status(response)
                collections.extend(response.json().get("custom_collections", []))
                next_link = response.links.get("next", {})
                url = next_link.get("url")
                params = None

        return collections

    async def create_custom_collection(self, title: str) -> dict[str, Any]:
        url = f"{self.base_url}/custom_collections.json"
        payload = {"custom_collection": {"title": title}}
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.post(
                url,
                json=payload,
                headers=self.headers,
                timeout=30.0,
            )
            _raise_for_status(response)
            return response.json()["custom_collection"]

    async def ensure_custom_collection(self, title: str) -> dict[str, Any]:
        normalized_title = title.strip().casefold()
        for collection in await self.list_custom_collections():
            if str(collection.get("title") or "").strip().casefold() == normalized_title:
                result = dict(collection)
                result["sync_status"] = "exists"
                return result

        collection = await self.create_custom_collection(title.strip())
        collection["sync_status"] = "created"
        return collection

    async def get_or_create_custom_collection(self, title: str) -> dict[str, Any]:
        return await self.ensure_custom_collection(title)

    async def list_collects(self, product_id: int | None = None, collection_id: int | None = None) -> list[dict[str, Any]]:
        url = f"{self.base_url}/collects.json"
        params: dict[str, Any] = {"limit": 250}
        if product_id is not None:
            params["product_id"] = product_id
        if collection_id is not None:
            params["collection_id"] = collection_id
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await _send_with_retries(
                lambda: client.get(url, params=params, headers=self.headers, timeout=30.0)
            )
            return response.json().get("collects", [])

    async def ensure_collect(self, product_id: int, collection_id: int) -> dict[str, Any]:
        for collect in await self.list_collects(product_id=product_id, collection_id=collection_id):
            if int(collect.get("product_id") or 0) == product_id and int(collect.get("collection_id") or 0) == collection_id:
                result = dict(collect)
                result["sync_status"] = "exists"
                return result

        url = f"{self.base_url}/collects.json"
        payload = {"collect": {"product_id": product_id, "collection_id": collection_id}}
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await _send_with_retries(
                lambda: client.post(url, json=payload, headers=self.headers, timeout=30.0)
            )
            collect = response.json()["collect"]
            collect["sync_status"] = "created"
            return collect

    async def create_customer(self, customer: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/customers.json"
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.post(
                url,
                json={"customer": customer},
                headers=self.headers,
                timeout=30.0,
            )
            _raise_for_status(response)
            return response.json()["customer"]

    async def update_customer(self, shopify_customer_id: int, customer: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/customers/{shopify_customer_id}.json"
        payload = dict(customer)
        payload["id"] = shopify_customer_id
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.put(
                url,
                json={"customer": payload},
                headers=self.headers,
                timeout=30.0,
            )
            _raise_for_status(response)
            return response.json()["customer"]

    async def list_locations(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/locations.json"
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(url, headers=self.headers, timeout=30.0)
            _raise_for_status(response)
            return response.json().get("locations", [])

    async def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/graphql.json"
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.post(
                url,
                json={"query": query, "variables": variables or {}},
                headers=self.headers,
                timeout=30.0,
            )
            _raise_for_status(response)
            return response.json()

    async def create_location(self, location: dict[str, Any]) -> dict[str, Any]:
        query = """
        mutation createLocation($input: LocationAddInput!) {
          locationAdd(input: $input) {
            location {
              id
              legacyResourceId
              name
              fulfillsOnlineOrders
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        data = await self.graphql(query, {"input": location})
        _raise_graphql_errors(data, "locationAdd")
        created = data["data"]["locationAdd"]["location"]
        created["sync_status"] = "created"
        return created

    async def list_inventory_levels(self, inventory_item_ids: list[int], limit: int = 250) -> list[dict[str, Any]]:
        levels: list[dict[str, Any]] = []
        if not inventory_item_ids:
            return levels

        async with httpx.AsyncClient(trust_env=False) as client:
            for index in range(0, len(inventory_item_ids), 50):
                ids = inventory_item_ids[index:index + 50]
                url = f"{self.base_url}/inventory_levels.json"
                params: dict[str, Any] | None = {
                    "inventory_item_ids": ",".join(str(item_id) for item_id in ids),
                    "limit": min(limit, 250),
                }
                while url:
                    response = await _send_with_retries(
                        lambda: client.get(url, params=params, headers=self.headers, timeout=30.0)
                    )
                    levels.extend(response.json().get("inventory_levels", []))
                    next_link = response.links.get("next", {})
                    url = next_link.get("url")
                    params = None

        return levels

    async def set_inventory_level(
        self,
        inventory_item_id: int,
        location_id: int,
        available: int,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/inventory_levels/set.json"
        payload = {
            "inventory_item_id": inventory_item_id,
            "location_id": location_id,
            "available": available,
            "disconnect_if_necessary": True,
        }
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await _send_with_retries(
                lambda: client.post(url, json=payload, headers=self.headers, timeout=30.0)
            )
            return response.json().get("inventory_level", {})

    async def upload_product_image(self, product_id: int, base64_data: str, filename: str | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/products/{product_id}/images.json"
        image: dict[str, Any] = {"attachment": base64_data}
        if filename:
            image["filename"] = filename
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await _send_with_retries(
                lambda: client.post(url, json={"image": image}, headers=self.headers, timeout=30.0)
            )
            return response.json().get("image", {})

    async def list_fulfillment_orders(self, shopify_order_id: int) -> list[dict[str, Any]]:
        url = f"{self.base_url}/orders/{shopify_order_id}/fulfillment_orders.json"
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await _send_with_retries(
                lambda: client.get(url, headers=self.headers, timeout=30.0)
            )
            return response.json().get("fulfillment_orders", [])

    async def create_fulfillment(
        self,
        fulfillment_order_ids: list[int],
        notify_customer: bool = False,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/fulfillments.json"
        payload = {
            "fulfillment": {
                "notify_customer": notify_customer,
                "line_items_by_fulfillment_order": [
                    {"fulfillment_order_id": fulfillment_order_id}
                    for fulfillment_order_id in fulfillment_order_ids
                ],
            }
        }
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await _send_with_retries(
                lambda: client.post(url, json=payload, headers=self.headers, timeout=30.0)
            )
            return response.json().get("fulfillment", {})

    async def fulfill_order(self, shopify_order_id: int, notify_customer: bool = False) -> dict[str, Any]:
        fulfillment_orders = await self.list_fulfillment_orders(shopify_order_id)
        fulfillment_order_ids = [
            int(fulfillment_order["id"])
            for fulfillment_order in fulfillment_orders
            if fulfillment_order.get("id") is not None
            and str(fulfillment_order.get("status") or "").lower() in {"open", "in_progress", "scheduled"}
        ]
        if not fulfillment_order_ids:
            return {"status": "skipped", "reason": "no_open_fulfillment_orders"}
        fulfillment = await self.create_fulfillment(fulfillment_order_ids, notify_customer=notify_customer)
        return {"status": "fulfilled", "fulfillment": fulfillment}

    async def get_inventory_item(self, inventory_item_id: int) -> dict[str, Any]:
        url = f"{self.base_url}/inventory_items/{inventory_item_id}.json"
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(url, headers=self.headers, timeout=30.0)
            _raise_for_status(response)
            return response.json().get("inventory_item", {})

    async def update_order_status(self, shopify_order_id: int, financial_status: str) -> dict[str, Any]:
        url = f"{self.base_url}/orders/{shopify_order_id}.json"
        payload = {"order": {"id": shopify_order_id, "financial_status": financial_status}}
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.put(url, json=payload, headers=self.headers, timeout=30.0)
            _raise_for_status(response)
            return response.json()

    async def update_order_financial_status(self, shopify_order_id: int, financial_status: str) -> dict[str, Any]:
        return await self.update_order_status(shopify_order_id, financial_status)
