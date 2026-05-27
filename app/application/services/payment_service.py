import httpx

from app.core.exceptions import ShopifyPaymentError
from app.infrastructure.repositories.order_repository import OrderRepository
from app.infrastructure.repositories.payment_repository import PaymentRepository
from app.infrastructure.repositories.payment_method_repository import PaymentMethodRepository
from app.infrastructure.shopify.client import ShopifyClient
from app.core.payment_methods import normalize_payment_method
from app.domain.models.payment import Payment

class PaymentService:
    def __init__(
        self,
        order_repo: OrderRepository,
        payment_repo: PaymentRepository,
        payment_method_repo: PaymentMethodRepository,
        shopify_client: ShopifyClient,
    ) -> None:
        self.order_repo = order_repo
        self.payment_repo = payment_repo
        self.payment_method_repo = payment_method_repo
        self.shopify_client = shopify_client

    async def confirm_manual_payment(
        self,
        order_id: int,
        method_code: str,
    ) -> Payment | None:
        order = await self.order_repo.get_by_shopify_id(order_id)
        if not order and order_id <= 2_147_483_647:
            order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise ShopifyPaymentError("Order not found")
        if order.financial_status == "paid" or order.status == "paid":
            raise ShopifyPaymentError("Order is already paid")

        normalized_method = normalize_payment_method(method_code)
        if not normalized_method:
            raise ShopifyPaymentError("Invalid payment method code")

        payment_method = await self.payment_method_repo.get_by_code(normalized_method)
        if not payment_method:
            raise ShopifyPaymentError("Invalid payment method code")

        order.is_offline_payment = True
        order.payment_method_id = payment_method.id

        amount = float(order.total_price)
        if amount <= 0:
            raise ShopifyPaymentError("Order total must be greater than zero")

        try:
            updated = await self.shopify_client.create_manual_payment_transaction(
                shopify_order_id=order.shopify_order_id,
                amount=amount,
                currency=order.currency,
                gateway="manual",
            )
            transaction = updated.get("transaction", {})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 422:
                await self.shopify_client.update_order_status(order.shopify_order_id, "paid")
                transaction = {}
            else:
                raise

        payment = Payment(
            order_id=order.id,
            payment_method_id=payment_method.id,
            amount=amount,
            currency=order.currency,
            status="success",
            shopify_transaction_id=str(transaction.get("id", "")) or None,
        )
        payment = await self.payment_repo.add(payment)

        order.status = "paid"
        order.financial_status = "paid"
        await self.order_repo.save(order)

        return payment

    async def list_payments(self) -> list[Payment]:
        return await self.payment_repo.list_all()
