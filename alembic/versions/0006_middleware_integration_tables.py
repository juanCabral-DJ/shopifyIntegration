"""add middleware integration tables

Revision ID: 0006_integration
Revises: 0005_order_line_items
Create Date: 2026-05-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_integration"
down_revision = "0005_order_line_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_inbox",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_event_inbox_topic", "event_inbox", ["topic"])
    op.create_index("ix_event_inbox_external_id", "event_inbox", ["external_id"])
    op.create_index("ix_event_inbox_status", "event_inbox", ["status", "received_at"])

    op.create_table(
        "event_outbox",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("target", sa.String(length=50), nullable=False),
        sa.Column("operation", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_event_outbox_operation", "event_outbox", ["operation"])
    op.create_index("ix_event_outbox_status", "event_outbox", ["status", "next_retry_at"])

    op.create_table(
        "map_order_ids",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("shopify_order_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("shopify_order_name", sa.String(length=128), nullable=False),
        sa.Column("factrx_movil_id", sa.String(length=128), nullable=True, unique=True),
        sa.Column("factrx_numero", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="created"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_map_order_ids_shopify_order_id", "map_order_ids", ["shopify_order_id"])
    op.create_index("ix_map_order_ids_factrx_numero", "map_order_ids", ["factrx_numero"])

    op.create_table(
        "map_sku_variant",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("invtim_codigo", sa.Integer(), nullable=False, unique=True),
        sa.Column("sku", sa.String(length=128), nullable=False),
        sa.Column("shopify_product_id", sa.BigInteger(), nullable=True),
        sa.Column("shopify_variant_id", sa.BigInteger(), nullable=True, unique=True),
        sa.Column("shopify_inventory_item_id", sa.BigInteger(), nullable=True, unique=True),
        sa.Column("last_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_map_sku_variant_sku", "map_sku_variant", ["sku"])
    op.create_index("ix_map_sku_variant_shopify_variant_id", "map_sku_variant", ["shopify_variant_id"])

    op.create_table(
        "map_cliente_customer",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("cxccte_codigo", sa.Integer(), nullable=False, unique=True),
        sa.Column("shopify_customer_id", sa.BigInteger(), nullable=True, unique=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_map_cliente_customer_email", "map_cliente_customer", ["email"])

    op.create_table(
        "map_invoices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("shopify_order_id", sa.BigInteger(), nullable=False),
        sa.Column("factrx_numero", sa.String(length=128), nullable=False),
        sa.Column("admncf_serial", sa.String(length=50), nullable=True),
        sa.Column("ncf", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("pdf_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_map_invoices_shopify_order_id", "map_invoices", ["shopify_order_id"])

    op.create_table(
        "map_recibos",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("shopify_order_id", sa.BigInteger(), nullable=False),
        sa.Column("eftrcb_numero", sa.Integer(), nullable=False, unique=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("payment_source", sa.String(length=128), nullable=True),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("balance_pending", sa.Numeric(14, 2), nullable=True),
        sa.Column("shopify_update_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_map_recibos_shopify_order_id", "map_recibos", ["shopify_order_id"])

    op.create_table(
        "map_sucursales_locations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("admsuc_codigo", sa.Integer(), nullable=False, unique=True),
        sa.Column("shopify_location_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "stg_inventory_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("invtim_codigo", sa.Integer(), nullable=False),
        sa.Column("admsuc_codigo", sa.Integer(), nullable=True),
        sa.Column("se_stock", sa.Numeric(14, 4), nullable=False),
        sa.Column("mobile_physical_stock", sa.Numeric(14, 4), nullable=True),
        sa.Column("shopify_stock", sa.Numeric(14, 4), nullable=True),
        sa.Column("reconciled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_payload", sa.JSON(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_stg_inventory_snapshots_invtim_codigo", "stg_inventory_snapshots", ["invtim_codigo"])
    op.create_index("ix_stg_inventory_snapshots_admsuc_codigo", "stg_inventory_snapshots", ["admsuc_codigo"])
    op.create_index("ix_stg_inventory_snapshots_reconciled", "stg_inventory_snapshots", ["reconciled"])

    op.create_table(
        "map_parametros_cache",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sync_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stats", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_sync_runs_sync_type", "sync_runs", ["sync_type"])
    op.create_index("ix_sync_runs_status", "sync_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_sync_runs_status", table_name="sync_runs")
    op.drop_index("ix_sync_runs_sync_type", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_table("map_parametros_cache")
    op.drop_index("ix_stg_inventory_snapshots_reconciled", table_name="stg_inventory_snapshots")
    op.drop_index("ix_stg_inventory_snapshots_admsuc_codigo", table_name="stg_inventory_snapshots")
    op.drop_index("ix_stg_inventory_snapshots_invtim_codigo", table_name="stg_inventory_snapshots")
    op.drop_table("stg_inventory_snapshots")
    op.drop_table("map_sucursales_locations")
    op.drop_index("ix_map_recibos_shopify_order_id", table_name="map_recibos")
    op.drop_table("map_recibos")
    op.drop_index("ix_map_invoices_shopify_order_id", table_name="map_invoices")
    op.drop_table("map_invoices")
    op.drop_index("ix_map_cliente_customer_email", table_name="map_cliente_customer")
    op.drop_table("map_cliente_customer")
    op.drop_index("ix_map_sku_variant_shopify_variant_id", table_name="map_sku_variant")
    op.drop_index("ix_map_sku_variant_sku", table_name="map_sku_variant")
    op.drop_table("map_sku_variant")
    op.drop_index("ix_map_order_ids_factrx_numero", table_name="map_order_ids")
    op.drop_index("ix_map_order_ids_shopify_order_id", table_name="map_order_ids")
    op.drop_table("map_order_ids")
    op.drop_index("ix_event_outbox_status", table_name="event_outbox")
    op.drop_index("ix_event_outbox_operation", table_name="event_outbox")
    op.drop_table("event_outbox")
    op.drop_index("ix_event_inbox_status", table_name="event_inbox")
    op.drop_index("ix_event_inbox_external_id", table_name="event_inbox")
    op.drop_index("ix_event_inbox_topic", table_name="event_inbox")
    op.drop_table("event_inbox")
