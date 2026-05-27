import pytest

from app.application.services.order_service import OrderService
from app.domain.models.customer import Customer


class FakeOrderRepo:
    def __init__(self):
        self.orders = {}
        self.next_id = 1

    async def get_by_shopify_id(self, shopify_order_id):
        return self.orders.get(shopify_order_id)

    async def add(self, order):
        order.id = self.next_id
        self.next_id += 1
        self.orders[order.shopify_order_id] = order
        return order

    async def save(self, order):
        self.orders[order.shopify_order_id] = order
        return order


class FakeCustomerRepo:
    async def get_or_create(self, shopify_customer_id, email, first_name, last_name):
        return Customer(
            id=1,
            shopify_customer_id=shopify_customer_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
        )


class FakePaymentMethodRepo:
    async def get_by_code(self, code):
        class Method:
            id = 1

        return Method()


class FakeShopifyClient:
    async def list_orders(self, status="any"):
        return [
            {
                "id": 100,
                "name": "#100",
                "email": "ada@example.com",
                "total_price": "25.00",
                "currency": "USD",
                "financial_status": "pending",
                "fulfillment_status": None,
                "line_items": [
                    {
                        "id": 300,
                        "product_id": 400,
                        "variant_id": 500,
                        "title": "Manual payment product",
                        "quantity": 2,
                        "price": "12.50",
                    }
                ],
                "payment_gateway_names": ["Cash"],
                "customer": {
                    "id": 200,
                    "email": "ada@example.com",
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                },
            }
        ]


@pytest.mark.asyncio
async def test_sync_from_shopify_creates_and_updates_orders() -> None:
    order_repo = FakeOrderRepo()
    service = OrderService(
        order_repo=order_repo,
        customer_repo=FakeCustomerRepo(),
        payment_method_repo=FakePaymentMethodRepo(),
    )

    first_result = await service.sync_from_shopify(FakeShopifyClient())
    second_result = await service.sync_from_shopify(FakeShopifyClient())

    order = order_repo.orders[100]
    assert first_result == {"synced": 1, "created": 1, "updated": 0}
    assert second_result == {"synced": 1, "created": 0, "updated": 1}
    assert order.status == "pending_payment"
    assert order.is_offline_payment is True
    assert order.payment_method_id == 1
    assert len(order.line_items) == 1
    assert order.line_items[0].shopify_line_item_id == 300
    assert order.line_items[0].shopify_product_id == 400
    assert order.line_items[0].shopify_variant_id == 500
    assert order.line_items[0].title == "Manual payment product"
    assert order.line_items[0].quantity == 2
    assert order.line_items[0].price == "12.50"


@pytest.mark.asyncio
async def test_sync_from_shopify_updates_existing_line_items_in_place() -> None:
    order_repo = FakeOrderRepo()
    service = OrderService(
        order_repo=order_repo,
        customer_repo=FakeCustomerRepo(),
        payment_method_repo=FakePaymentMethodRepo(),
    )

    await service.sync_from_shopify(FakeShopifyClient())
    original_line_item = order_repo.orders[100].line_items[0]

    await service.sync_from_shopify(FakeShopifyClient())

    order = order_repo.orders[100]
    assert len(order.line_items) == 1
    assert order.line_items[0] is original_line_item
    assert order.line_items[0].shopify_line_item_id == 300
