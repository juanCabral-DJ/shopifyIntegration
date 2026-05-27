from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.infrastructure.db import Base

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    payment_method_id = Column(Integer, ForeignKey("payment_methods.id"), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    shopify_transaction_id = Column(String(128), nullable=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())

    order = relationship("Order", back_populates="payments")
    payment_method = relationship("PaymentMethod")
