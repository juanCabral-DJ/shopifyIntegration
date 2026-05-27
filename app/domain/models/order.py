from sqlalchemy import BigInteger, Column, Integer, String, Numeric, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.infrastructure.db import Base

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    shopify_order_id = Column(BigInteger, unique=True, nullable=False)
    name = Column(String(128), nullable=False)
    email = Column(String(255), nullable=True)
    total_price = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), nullable=False)
    financial_status = Column(String(50), nullable=False)
    fulfillment_status = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="open")
    is_offline_payment = Column(Boolean, nullable=False, default=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    payment_method_id = Column(Integer, ForeignKey("payment_methods.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    customer = relationship("Customer", backref="orders")
    payments = relationship("Payment", back_populates="order")
    payment_method = relationship("PaymentMethod")
    line_items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    @property
    def customer_email(self) -> str | None:
        return self.email or (self.customer.email if self.customer else None)
