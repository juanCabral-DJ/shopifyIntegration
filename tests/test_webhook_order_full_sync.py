import pytest

from app.application.services.webhook_service import WebhookService
from tests.test_order_sync import FakeCustomerRepo, FakeOrderRepo, FakePaymentMethodRepo, FakeShopifyClient


class FakeWebhookRepo:
    def __init__(self):
        self.events = []

    async def add_event(self, topic, payload, headers, verified, attempt_count):
        self.events.append(
            {
                "topic": topic,
                "payload": payload,
                "headers": headers,
                "verified": verified,
                "attempt_count": attempt_count,
            }
        )


@pytest.mark.asyncio
async def test_order_create_webhook_syncs_all_orders_from_shopify() -> None:
    order_repo = FakeOrderRepo()
    service = WebhookService(
        webhook_repo=FakeWebhookRepo(),
        order_repo=order_repo,
        customer_repo=FakeCustomerRepo(),
        payment_method_repo=FakePaymentMethodRepo(),
        shopify_client=FakeShopifyClient(),
    )

    await service.handle_order_event({"id": 999}, "orders/create", 1)

    assert 100 in order_repo.orders
    assert 999 not in order_repo.orders
