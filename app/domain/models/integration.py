import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.infrastructure.db import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


def purge_after_30_days() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=30)


class EventInbox(Base):
    __tablename__ = "event_inbox"

    id = Column(String(36), primary_key=True, default=new_uuid)
    source = Column(String(50), nullable=False)
    topic = Column(String(128), nullable=False, index=True)
    external_id = Column(String(128), nullable=True, index=True)
    payload = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    purge_after = Column(DateTime(timezone=True), nullable=False, default=purge_after_30_days)


class EventOutbox(Base):
    __tablename__ = "event_outbox"

    id = Column(String(36), primary_key=True, default=new_uuid)
    target = Column(String(50), nullable=False)
    operation = Column(String(128), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    response = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    purge_after = Column(DateTime(timezone=True), nullable=False, default=purge_after_30_days)


class MapOrderIds(Base):
    __tablename__ = "map_order_ids"

    id = Column(String(36), primary_key=True, default=new_uuid)
    shopify_order_id = Column(BigInteger, unique=True, nullable=False, index=True)
    shopify_order_name = Column(String(128), nullable=False)
    factrx_movil_id = Column(String(128), unique=True, nullable=True)
    factrx_numero = Column(String(128), nullable=True, index=True)
    status = Column(String(50), nullable=False, default="created")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)


class MapSkuVariant(Base):
    __tablename__ = "map_sku_variant"

    id = Column(String(36), primary_key=True, default=new_uuid)
    invitm_codigo = Column(Integer, unique=True, nullable=False)
    sku = Column(String(128), nullable=False, index=True)
    shopify_product_id = Column(BigInteger, nullable=True)
    shopify_variant_id = Column(BigInteger, unique=True, nullable=True, index=True)
    shopify_inventory_item_id = Column(BigInteger, unique=True, nullable=True)
    last_price = Column(Numeric(14, 2), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)


class MapProductImage(Base):
    __tablename__ = "map_product_images"

    id = Column(String(36), primary_key=True, default=new_uuid)
    external_image_id = Column(String(255), unique=True, nullable=False, index=True)
    invitm_codigo = Column(Integer, nullable=False, index=True)
    admimg_linea = Column(Integer, nullable=True)
    image_hash = Column(String(64), nullable=False, index=True)
    shopify_product_id = Column(BigInteger, nullable=False, index=True)
    shopify_image_id = Column(BigInteger, unique=True, nullable=True, index=True)
    filename = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("invitm_codigo", "image_hash", name="uq_map_product_images_item_hash"),
    )


class MapClienteCustomer(Base):
    __tablename__ = "map_cliente_customer"

    id = Column(String(36), primary_key=True, default=new_uuid)
    cxccte_codigo = Column(Integer, unique=True, nullable=False)
    shopify_customer_id = Column(BigInteger, unique=True, nullable=True)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(50), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)


class MapInvoices(Base):
    __tablename__ = "map_invoices"

    id = Column(String(36), primary_key=True, default=new_uuid)
    shopify_order_id = Column(BigInteger, nullable=False, index=True)
    factrx_numero = Column(String(128), nullable=False)
    admncf_serial = Column(String(50), nullable=True)
    ncf = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    payload = Column(JSON, nullable=True)
    pdf_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MapRecibos(Base):
    __tablename__ = "map_recibos"

    id = Column(String(36), primary_key=True, default=new_uuid)
    shopify_order_id = Column(BigInteger, nullable=False, index=True)
    eftrcb_numero = Column(Integer, unique=True, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(10), nullable=True)
    payment_source = Column(String(128), nullable=True)
    reference = Column(String(255), nullable=True)
    balance_pending = Column(Numeric(14, 2), nullable=True)
    shopify_update_attempts = Column(Integer, nullable=False, default=0)
    status = Column(String(50), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MapSucursalesLocations(Base):
    __tablename__ = "map_sucursales_locations"

    id = Column(String(36), primary_key=True, default=new_uuid)
    admsuc_codigo = Column(Integer, unique=True, nullable=False)
    shopify_location_id = Column(BigInteger, unique=True, nullable=True)
    name = Column(String(255), nullable=True)
    active = Column(Boolean, nullable=False, default=True)


class MapFamiliasCollections(Base):
    __tablename__ = "map_familias_collections"

    id = Column(String(36), primary_key=True, default=new_uuid)
    se_familia_id = Column(String(128), unique=True, nullable=False)
    se_familia_nombre = Column(String(255), nullable=True)
    shopify_collection_id = Column(BigInteger, unique=True, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)


class MapMarcasTags(Base):
    __tablename__ = "map_marcas_tags"

    id = Column(String(36), primary_key=True, default=new_uuid)
    se_marca_id = Column(String(128), unique=True, nullable=False)
    se_marca_nombre = Column(String(255), nullable=True)
    shopify_tag = Column(String(255), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)


class InventorySnapshot(Base):
    __tablename__ = "stg_inventory_snapshots"

    id = Column(String(36), primary_key=True, default=new_uuid)
    invitm_codigo = Column(Integer, nullable=False, index=True)
    admsuc_codigo = Column(Integer, nullable=True, index=True)
    se_stock = Column(Numeric(14, 4), nullable=False)
    mobile_physical_stock = Column(Numeric(14, 4), nullable=True)
    shopify_stock = Column(Numeric(14, 4), nullable=True)
    reconciled = Column(Boolean, nullable=False, default=False, index=True)
    source_payload = Column(JSON, nullable=True)
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MapParametrosCache(Base):
    __tablename__ = "map_parametros_cache"

    key = Column(String(128), primary_key=True)
    value = Column(JSON, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id = Column(String(36), primary_key=True, default=new_uuid)
    sync_type = Column(String(80), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="running", index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    stats = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
