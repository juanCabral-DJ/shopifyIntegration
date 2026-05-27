from app.infrastructure.repositories.order_repository import OrderRepository
from app.infrastructure.repositories.customer_repository import CustomerRepository
from app.infrastructure.repositories.payment_method_repository import PaymentMethodRepository
from app.core.config import settings
from app.core.payment_methods import normalize_payment_method
from app.domain.models.order import Order
from app.domain.models.order_item import OrderItem

class OrderService:
    def __init__(
        self,
        order_repo: OrderRepository,
        customer_repo: CustomerRepository | None = None,
        payment_method_repo: PaymentMethodRepository | None = None,
    ) -> None:
        self.order_repo = order_repo
        self.customer_repo = customer_repo
        self.payment_method_repo = payment_method_repo

    async def list_orders(self) -> list[Order]:
        return await self.order_repo.list_all()

    async def get_order_by_id(self, order_id: int) -> Order | None:
        return await self.order_repo.get_by_id(order_id)

    async def sync_from_shopify(self, shopify_client) -> dict[str, int]:
        shopify_orders = await shopify_client.list_orders(status="any")
        created = 0
        updated = 0

        for payload in shopify_orders:
            existing = await self.order_repo.get_by_shopify_id(int(payload["id"]))
            await self.create_or_update_from_shopify(payload)
            if existing:
                updated += 1
            else:
                created += 1

        return {
            "synced": len(shopify_orders),
            "created": created,
            "updated": updated,
        }

    async def create_or_update_from_shopify(self, payload: dict) -> Order:
        shopify_order_id = int(payload["id"])
        customer_payload = payload.get("customer") or {}
        customer_id = customer_payload.get("id")
        customer = None
        if self.customer_repo and customer_id:
            customer = await self.customer_repo.get_or_create(
                shopify_customer_id=int(customer_id),
                email=customer_payload.get("email"),
                first_name=customer_payload.get("first_name"),
                last_name=customer_payload.get("last_name"),
            )

        order = await self.order_repo.get_by_shopify_id(shopify_order_id)
        is_offline = self._detect_offline_payment(payload)
        financial_status = payload.get("financial_status", "pending")
        fulfillment_status = payload.get("fulfillment_status")
        if order is None:
            order = Order(
                shopify_order_id=shopify_order_id,
                name=payload.get("name", ""),
                email=payload.get("email"),
                total_price=payload.get("total_price", 0.0),
                currency=payload.get("currency", payload.get("currency_code", "USD")),
                financial_status=financial_status,
                fulfillment_status=fulfillment_status,
                status="pending_payment" if is_offline else "open",
                is_offline_payment=is_offline,
                customer=customer,
            )
            order.line_items = self._build_line_items(payload)
            if is_offline and self.payment_method_repo:
                method = await self._find_payment_method(payload)
                if method:
                    order.payment_method_id = method.id
            order = await self.order_repo.add(order)
        else:
            order.name = payload.get("name", order.name)
            order.email = payload.get("email", order.email)
            order.total_price = payload.get("total_price", order.total_price)
            order.currency = payload.get("currency", order.currency)
            order.financial_status = financial_status
            order.fulfillment_status = fulfillment_status
            if "line_items" in payload:
                self._sync_line_items(order, payload)
            order.is_offline_payment = is_offline
            if customer:
                order.customer_id = customer.id
            if order.status != "paid":
                order.status = "pending_payment" if is_offline else order.status
            if is_offline and self.payment_method_repo:
                method = await self._find_payment_method(payload)
                if method:
                    order.payment_method_id = method.id
            order = await self.order_repo.save(order)

        return order

    def _sync_line_items(self, order: Order, payload: dict) -> None:
        existing_by_shopify_id = {
            item.shopify_line_item_id: item
            for item in order.line_items
        }
        seen_ids = set()

        for payload_item in payload.get("line_items", []):
            shopify_line_item_id = payload_item.get("id")
            if shopify_line_item_id is None:
                continue
            shopify_line_item_id = int(shopify_line_item_id)
            seen_ids.add(shopify_line_item_id)

            order_item = existing_by_shopify_id.get(shopify_line_item_id)
            if order_item is None:
                order_item = OrderItem(shopify_line_item_id=shopify_line_item_id)
                order.line_items.append(order_item)

            self._apply_line_item_payload(order_item, payload_item)

        order.line_items[:] = [
            item
            for item in order.line_items
            if item.shopify_line_item_id in seen_ids
        ]

    def _build_line_items(self, payload: dict) -> list[OrderItem]:
        line_items = []
        for item in payload.get("line_items", []):
            if item.get("id") is None:
                continue
            order_item = OrderItem(shopify_line_item_id=int(item["id"]))
            self._apply_line_item_payload(order_item, item)
            line_items.append(order_item)
        return line_items

    def _apply_line_item_payload(self, order_item: OrderItem, payload: dict) -> None:
        order_item.shopify_product_id = self._optional_int(payload.get("product_id"))
        order_item.shopify_variant_id = self._optional_int(payload.get("variant_id"))
        order_item.sku = payload.get("sku")
        order_item.title = payload.get("title") or payload.get("name") or ""
        order_item.variant_title = payload.get("variant_title")
        order_item.quantity = int(payload.get("quantity") or 0)
        order_item.price = payload.get("price") or 0
        order_item.fulfillment_status = payload.get("fulfillment_status")

    def _optional_int(self, value) -> int | None:
        if value is None:
            return None
        return int(value)

    def _detect_offline_payment(self, payload: dict) -> bool:
        return self._get_normalized_payment_method(payload) in settings.offline_payment_methods

    async def _find_payment_method(self, payload: dict):
        if not self.payment_method_repo:
            return None
        normalized_method = self._get_normalized_payment_method(payload)
        if normalized_method:
            return await self.payment_method_repo.get_by_code(normalized_method)
        return None

    def _get_normalized_payment_method(self, payload: dict) -> str | None:
        for gateway in payload.get("payment_gateway_names", []):
            normalized = normalize_payment_method(str(gateway))
            if normalized:
                return normalized
        if payload.get("gateway"):
            return normalize_payment_method(str(payload["gateway"]))
        return None
