from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.infrastructure.db import Base


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("inventory_item_id", "location_id", name="uq_inventory_item_location"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shopify_product_id = Column(BigInteger, nullable=False, index=True)
    shopify_variant_id = Column(BigInteger, nullable=False, index=True)
    inventory_item_id = Column(BigInteger, nullable=False, index=True)
    location_id = Column(BigInteger, nullable=False, index=True)
    sku = Column(String(128), nullable=True, index=True)
    product_title = Column(String(255), nullable=False)
    variant_title = Column(String(255), nullable=True)
    available = Column(Integer, nullable=True)
    tracked = Column(Boolean, nullable=False, default=True)
    shopify_updated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
