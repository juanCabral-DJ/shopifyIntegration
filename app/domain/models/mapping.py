import uuid

from sqlalchemy import BigInteger, Column, DateTime, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.infrastructure.db import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


class MappingColumnsMixin:
    id = Column(String(36), primary_key=True, default=new_uuid)
    sync_status = Column(String(32), nullable=False, default="pending", index=True)
    source_hash = Column(String(128), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)


class ProductMapping(MappingColumnsMixin, Base):
    __tablename__ = "product_mapping"

    external_product_id = Column(String(128), nullable=False, index=True)
    shopify_product_id = Column(BigInteger, nullable=True, index=True)
    sku = Column(String(128), nullable=True, index=True)
    payload_hash = Column(String(128), nullable=True)

    __table_args__ = (
        UniqueConstraint("external_product_id", name="uq_product_mapping_external_product_id"),
        UniqueConstraint("shopify_product_id", name="uq_product_mapping_shopify_product_id"),
    )


class VariantMapping(MappingColumnsMixin, Base):
    __tablename__ = "variant_mapping"

    external_variant_id = Column(String(128), nullable=False, index=True)
    external_product_id = Column(String(128), nullable=True, index=True)
    shopify_product_id = Column(BigInteger, nullable=True, index=True)
    shopify_variant_id = Column(BigInteger, nullable=True, index=True)
    shopify_inventory_item_id = Column(BigInteger, nullable=True, index=True)
    sku = Column(String(128), nullable=False, index=True)
    price = Column(Numeric(14, 2), nullable=True)

    __table_args__ = (
        UniqueConstraint("external_variant_id", name="uq_variant_mapping_external_variant_id"),
        UniqueConstraint("shopify_variant_id", name="uq_variant_mapping_shopify_variant_id"),
        UniqueConstraint("shopify_inventory_item_id", name="uq_variant_mapping_inventory_item_id"),
    )


class OrderMapping(MappingColumnsMixin, Base):
    __tablename__ = "order_mapping"

    external_order_id = Column(String(128), nullable=True, index=True)
    shopify_order_id = Column(BigInteger, nullable=False, index=True)
    shopify_order_name = Column(String(128), nullable=True)
    external_invoice_id = Column(String(128), nullable=True, index=True)
    financial_status = Column(String(32), nullable=True)
    fulfillment_status = Column(String(32), nullable=True)

    __table_args__ = (
        UniqueConstraint("shopify_order_id", name="uq_order_mapping_shopify_order_id"),
        UniqueConstraint("external_order_id", name="uq_order_mapping_external_order_id"),
    )


class CustomerMapping(MappingColumnsMixin, Base):
    __tablename__ = "customer_mapping"

    external_customer_id = Column(String(128), nullable=False, index=True)
    shopify_customer_id = Column(BigInteger, nullable=True, index=True)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(50), nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("external_customer_id", name="uq_customer_mapping_external_customer_id"),
        UniqueConstraint("shopify_customer_id", name="uq_customer_mapping_shopify_customer_id"),
    )


class InventoryMapping(MappingColumnsMixin, Base):
    __tablename__ = "inventory_mapping"

    external_product_id = Column(String(128), nullable=False, index=True)
    external_variant_id = Column(String(128), nullable=True, index=True)
    external_branch_id = Column(String(128), nullable=False, index=True)
    shopify_inventory_item_id = Column(BigInteger, nullable=True, index=True)
    shopify_location_id = Column(BigInteger, nullable=True, index=True)
    available = Column(Numeric(14, 4), nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "external_product_id",
            "external_variant_id",
            "external_branch_id",
            name="uq_inventory_mapping_external_product_variant_branch",
        ),
    )


class BranchMapping(MappingColumnsMixin, Base):
    __tablename__ = "branch_mapping"

    external_branch_id = Column(String(128), nullable=False, index=True)
    shopify_location_id = Column(BigInteger, nullable=True, index=True)
    name = Column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("external_branch_id", name="uq_branch_mapping_external_branch_id"),
        UniqueConstraint("shopify_location_id", name="uq_branch_mapping_shopify_location_id"),
    )


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(String(36), primary_key=True, default=new_uuid)
    sync_type = Column(String(80), nullable=False, index=True)
    entity_type = Column(String(80), nullable=True, index=True)
    entity_id = Column(String(128), nullable=True, index=True)
    direction = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    message = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class FailedJob(Base):
    __tablename__ = "failed_jobs"

    id = Column(String(36), primary_key=True, default=new_uuid)
    queue = Column(String(80), nullable=False, index=True)
    job_type = Column(String(128), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=5)
    next_retry_at = Column(DateTime(timezone=True), nullable=True, index=True)
    failed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
