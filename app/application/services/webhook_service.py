from app.infrastructure.repositories.webhook_repository import WebhookRepository
from app.infrastructure.repositories.order_repository import OrderRepository
from app.infrastructure.repositories.customer_repository import CustomerRepository
from app.infrastructure.repositories.payment_method_repository import PaymentMethodRepository
from app.infrastructure.repositories.inventory_repository import InventoryRepository
from app.infrastructure.repositories.integration_repository import IntegrationRepository
from app.infrastructure.shopify.client import ShopifyClient
from app.application.services.inventory_service import InventoryService
from app.application.services.middleware_service import MiddlewareService
from app.application.services.order_service import OrderService

class WebhookService:
    def __init__(
        self,
        webhook_repo: WebhookRepository,
        order_repo: OrderRepository,
        customer_repo: CustomerRepository,
        payment_method_repo: PaymentMethodRepository,
        shopify_client: ShopifyClient,
        inventory_repo: InventoryRepository | None = None,
        integration_repo: IntegrationRepository | None = None,
    ) -> None:
        self.webhook_repo = webhook_repo
        self.order_repo = order_repo
        self.customer_repo = customer_repo
        self.payment_method_repo = payment_method_repo
        self.inventory_repo = inventory_repo
        self.integration_repo = integration_repo
        self.shopify_client = shopify_client

    async def handle_order_event(self, payload: dict, topic: str, attempt_count: int) -> None:
        verified = True
        headers = {"topic": topic, "attempt_count": attempt_count}
        await self.webhook_repo.add_event(topic, payload, headers, verified, attempt_count)
        if self.integration_repo:
            middleware = MiddlewareService(integration_repo=self.integration_repo)
            await middleware.register_shopify_event(topic, payload)
        service = OrderService(
            order_repo=self.order_repo,
            customer_repo=self.customer_repo,
            payment_method_repo=self.payment_method_repo,
        )
        if topic == "orders/create" and not self.integration_repo:
            await service.sync_from_shopify(self.shopify_client)
        elif topic in {"orders/create", "orders/updated", "orders/paid"}:
            await service.create_or_update_from_shopify(payload)

    async def handle_inventory_event(self, payload: dict, topic: str, attempt_count: int) -> None:
        verified = True
        headers = {"topic": topic, "attempt_count": attempt_count}
        await self.webhook_repo.add_event(topic, payload, headers, verified, attempt_count)
        if self.integration_repo:
            middleware = MiddlewareService(integration_repo=self.integration_repo)
            await middleware.register_shopify_event(topic, payload)
        if not self.inventory_repo:
            return

        service = InventoryService(
            inventory_repo=self.inventory_repo,
            shopify_client=self.shopify_client,
        )
        if topic == "inventory_levels/update":
            await service.handle_inventory_level_update(payload)
        elif topic == "inventory_items/update":
            await service.handle_inventory_item_update(payload)
        elif topic == "products/update":
            await service.handle_product_update(payload)
