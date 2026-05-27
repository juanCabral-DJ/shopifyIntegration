import pytest
from app.application.services.payment_service import PaymentService
from app.domain.models.payment import Payment
from app.core.exceptions import ShopifyPaymentError

class FakeOrder:
    def __init__(self):
        self.id = 1
        self.shopify_order_id = 100
        self.total_price = 100.0
        self.currency = "USD"
        self.is_offline_payment = True
        self.status = "pending_payment"
        self.financial_status = "pending"

class FakeOrderRepo:
    def __init__(self, order):
        self.order = order

    async def get_by_shopify_id(self, shopify_order_id):
        if self.order and shopify_order_id == self.order.shopify_order_id:
            return self.order
        return None

    async def get_by_id(self, order_id):
        return self.order

    async def save(self, order):
        return order

class FakePaymentRepo:
    async def add(self, payment: Payment):
        payment.id = 1
        return payment

class FakePaymentMethodRepo:
    async def get_by_code(self, code: str):
        class Method:
            id = 1
            code = "efectivo"
        if code == "efectivo":
            return Method()
        return None

class FakeShopifyClient:
    async def create_manual_payment_transaction(self, shopify_order_id, amount, currency, gateway):
        return {"transaction": {"id": "txn_123"}}

    async def update_order_payment(self, shopify_order_id, amount, currency):
        return {"transaction": {"id": "txn_123"}}

@pytest.mark.asyncio
async def test_confirm_manual_payment_success() -> None:
    order = FakeOrder()
    service = PaymentService(
        order_repo=FakeOrderRepo(order),
        payment_repo=FakePaymentRepo(),
        payment_method_repo=FakePaymentMethodRepo(),
        shopify_client=FakeShopifyClient(),
    )
    payment = await service.confirm_manual_payment(order_id=1, method_code="cash")
    assert payment.id == 1
    assert payment.amount == 100.0
    assert payment.currency == "USD"
    assert payment.status == "success"
    assert payment.shopify_transaction_id == "txn_123"

@pytest.mark.asyncio
async def test_confirm_manual_payment_accepts_shopify_order_id() -> None:
    order = FakeOrder()
    order.shopify_order_id = 7989501427810
    service = PaymentService(
        order_repo=FakeOrderRepo(order),
        payment_repo=FakePaymentRepo(),
        payment_method_repo=FakePaymentMethodRepo(),
        shopify_client=FakeShopifyClient(),
    )
    payment = await service.confirm_manual_payment(order_id=7989501427810, method_code="efectivo")

    assert payment.amount == 100.0
    assert payment.shopify_transaction_id == "txn_123"

@pytest.mark.asyncio
async def test_confirm_manual_payment_marks_order_as_offline() -> None:
    order = FakeOrder()
    order.is_offline_payment = False
    order.status = "open"
    service = PaymentService(
        order_repo=FakeOrderRepo(order),
        payment_repo=FakePaymentRepo(),
        payment_method_repo=FakePaymentMethodRepo(),
        shopify_client=FakeShopifyClient(),
    )

    await service.confirm_manual_payment(order_id=1, method_code="efectivo")

    assert order.is_offline_payment is True
    assert order.status == "paid"
    assert order.financial_status == "paid"

@pytest.mark.asyncio
async def test_confirm_manual_payment_invalid_method() -> None:
    order = FakeOrder()
    service = PaymentService(
        order_repo=FakeOrderRepo(order),
        payment_repo=FakePaymentRepo(),
        payment_method_repo=FakePaymentMethodRepo(),
        shopify_client=FakeShopifyClient(),
    )
    with pytest.raises(ShopifyPaymentError):
        await service.confirm_manual_payment(order_id=1, method_code="invalid")
