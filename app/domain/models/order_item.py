from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.infrastructure.db import Base


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "shopify_line_item_id", name="uq_order_line_item"),
    )

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    shopify_line_item_id = Column(BigInteger, nullable=False)
    shopify_product_id = Column(BigInteger, nullable=True, index=True)
    shopify_variant_id = Column(BigInteger, nullable=True, index=True)
    sku = Column(String(128), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    variant_title = Column(String(255), nullable=True)
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    fulfillment_status = Column(String(50), nullable=True)

    order = relationship("Order", back_populates="line_items")
