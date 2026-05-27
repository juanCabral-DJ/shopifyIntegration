"""add canonical integration mapping tables

Revision ID: 0008_canonical_mappings
Revises: 0007_align_se_contract_v14
Create Date: 2026-05-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_canonical_mappings"
down_revision = "0007_align_se_contract_v14"
branch_labels = None
depends_on = None


def _mapping_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sync_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("source_hash", sa.String(length=128), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "product_mapping",
        *_mapping_columns(),
        sa.Column("external_product_id", sa.String(length=128), nullable=False),
        sa.Column("shopify_product_id", sa.BigInteger(), nullable=True),
        sa.Column("sku", sa.String(length=128), nullable=True),
        sa.Column("payload_hash", sa.String(length=128), nullable=True),
        sa.UniqueConstraint("external_product_id", name="uq_product_mapping_external_product_id"),
        sa.UniqueConstraint("shopify_product_id", name="uq_product_mapping_shopify_product_id"),
    )
    op.create_index("ix_product_mapping_sync_status", "product_mapping", ["sync_status"])
    op.create_index("ix_product_mapping_external_product_id", "product_mapping", ["external_product_id"])
    op.create_index("ix_product_mapping_shopify_product_id", "product_mapping", ["shopify_product_id"])
    op.create_index("ix_product_mapping_sku", "product_mapping", ["sku"])

    op.create_table(
        "variant_mapping",
        *_mapping_columns(),
        sa.Column("external_variant_id", sa.String(length=128), nullable=False),
        sa.Column("external_product_id", sa.String(length=128), nullable=True),
        sa.Column("shopify_product_id", sa.BigInteger(), nullable=True),
        sa.Column("shopify_variant_id", sa.BigInteger(), nullable=True),
        sa.Column("shopify_inventory_item_id", sa.BigInteger(), nullable=True),
        sa.Column("sku", sa.String(length=128), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.UniqueConstraint("external_variant_id", name="uq_variant_mapping_external_variant_id"),
        sa.UniqueConstraint("shopify_variant_id", name="uq_variant_mapping_shopify_variant_id"),
        sa.UniqueConstraint("shopify_inventory_item_id", name="uq_variant_mapping_inventory_item_id"),
    )
    op.create_index("ix_variant_mapping_sync_status", "variant_mapping", ["sync_status"])
    op.create_index("ix_variant_mapping_external_variant_id", "variant_mapping", ["external_variant_id"])
    op.create_index("ix_variant_mapping_external_product_id", "variant_mapping", ["external_product_id"])
    op.create_index("ix_variant_mapping_shopify_product_id", "variant_mapping", ["shopify_product_id"])
    op.create_index("ix_variant_mapping_shopify_variant_id", "variant_mapping", ["shopify_variant_id"])
    op.create_index("ix_variant_mapping_shopify_inventory_item_id", "variant_mapping", ["shopify_inventory_item_id"])
    op.create_index("ix_variant_mapping_sku", "variant_mapping", ["sku"])

    op.create_table(
        "order_mapping",
        *_mapping_columns(),
        sa.Column("external_order_id", sa.String(length=128), nullable=True),
        sa.Column("shopify_order_id", sa.BigInteger(), nullable=False),
        sa.Column("shopify_order_name", sa.String(length=128), nullable=True),
        sa.Column("external_invoice_id", sa.String(length=128), nullable=True),
        sa.Column("financial_status", sa.String(length=32), nullable=True),
        sa.Column("fulfillment_status", sa.String(length=32), nullable=True),
        sa.UniqueConstraint("shopify_order_id", name="uq_order_mapping_shopify_order_id"),
        sa.UniqueConstraint("external_order_id", name="uq_order_mapping_external_order_id"),
    )
    op.create_index("ix_order_mapping_sync_status", "order_mapping", ["sync_status"])
    op.create_index("ix_order_mapping_external_order_id", "order_mapping", ["external_order_id"])
    op.create_index("ix_order_mapping_shopify_order_id", "order_mapping", ["shopify_order_id"])
    op.create_index("ix_order_mapping_external_invoice_id", "order_mapping", ["external_invoice_id"])

    op.create_table(
        "customer_mapping",
        *_mapping_columns(),
        sa.Column("external_customer_id", sa.String(length=128), nullable=False),
        sa.Column("shopify_customer_id", sa.BigInteger(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.UniqueConstraint("external_customer_id", name="uq_customer_mapping_external_customer_id"),
        sa.UniqueConstraint("shopify_customer_id", name="uq_customer_mapping_shopify_customer_id"),
    )
    op.create_index("ix_customer_mapping_sync_status", "customer_mapping", ["sync_status"])
    op.create_index("ix_customer_mapping_external_customer_id", "customer_mapping", ["external_customer_id"])
    op.create_index("ix_customer_mapping_shopify_customer_id", "customer_mapping", ["shopify_customer_id"])
    op.create_index("ix_customer_mapping_email", "customer_mapping", ["email"])
    op.create_index("ix_customer_mapping_phone", "customer_mapping", ["phone"])

    op.create_table(
        "inventory_mapping",
        *_mapping_columns(),
        sa.Column("external_product_id", sa.String(length=128), nullable=False),
        sa.Column("external_variant_id", sa.String(length=128), nullable=True),
        sa.Column("external_branch_id", sa.String(length=128), nullable=False),
        sa.Column("shopify_inventory_item_id", sa.BigInteger(), nullable=True),
        sa.Column("shopify_location_id", sa.BigInteger(), nullable=True),
        sa.Column("available", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "external_product_id",
            "external_variant_id",
            "external_branch_id",
            name="uq_inventory_mapping_external_product_variant_branch",
        ),
    )
    op.create_index("ix_inventory_mapping_sync_status", "inventory_mapping", ["sync_status"])
    op.create_index("ix_inventory_mapping_external_product_id", "inventory_mapping", ["external_product_id"])
    op.create_index("ix_inventory_mapping_external_variant_id", "inventory_mapping", ["external_variant_id"])
    op.create_index("ix_inventory_mapping_external_branch_id", "inventory_mapping", ["external_branch_id"])
    op.create_index("ix_inventory_mapping_shopify_inventory_item_id", "inventory_mapping", ["shopify_inventory_item_id"])
    op.create_index("ix_inventory_mapping_shopify_location_id", "inventory_mapping", ["shopify_location_id"])

    op.create_table(
        "branch_mapping",
        *_mapping_columns(),
        sa.Column("external_branch_id", sa.String(length=128), nullable=False),
        sa.Column("shopify_location_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.UniqueConstraint("external_branch_id", name="uq_branch_mapping_external_branch_id"),
        sa.UniqueConstraint("shopify_location_id", name="uq_branch_mapping_shopify_location_id"),
    )
    op.create_index("ix_branch_mapping_sync_status", "branch_mapping", ["sync_status"])
    op.create_index("ix_branch_mapping_external_branch_id", "branch_mapping", ["external_branch_id"])
    op.create_index("ix_branch_mapping_shopify_location_id", "branch_mapping", ["shopify_location_id"])

    op.create_table(
        "sync_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sync_type", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sync_logs_sync_type", "sync_logs", ["sync_type"])
    op.create_index("ix_sync_logs_entity_type", "sync_logs", ["entity_type"])
    op.create_index("ix_sync_logs_entity_id", "sync_logs", ["entity_id"])
    op.create_index("ix_sync_logs_status", "sync_logs", ["status"])

    op.create_table(
        "failed_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("queue", sa.String(length=80), nullable=False),
        sa.Column("job_type", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_failed_jobs_queue", "failed_jobs", ["queue"])
    op.create_index("ix_failed_jobs_job_type", "failed_jobs", ["job_type"])
    op.create_index("ix_failed_jobs_next_retry_at", "failed_jobs", ["next_retry_at"])


def downgrade() -> None:
    op.drop_index("ix_failed_jobs_next_retry_at", table_name="failed_jobs")
    op.drop_index("ix_failed_jobs_job_type", table_name="failed_jobs")
    op.drop_index("ix_failed_jobs_queue", table_name="failed_jobs")
    op.drop_table("failed_jobs")
    op.drop_index("ix_sync_logs_status", table_name="sync_logs")
    op.drop_index("ix_sync_logs_entity_id", table_name="sync_logs")
    op.drop_index("ix_sync_logs_entity_type", table_name="sync_logs")
    op.drop_index("ix_sync_logs_sync_type", table_name="sync_logs")
    op.drop_table("sync_logs")
    op.drop_index("ix_branch_mapping_shopify_location_id", table_name="branch_mapping")
    op.drop_index("ix_branch_mapping_external_branch_id", table_name="branch_mapping")
    op.drop_index("ix_branch_mapping_sync_status", table_name="branch_mapping")
    op.drop_table("branch_mapping")
    op.drop_index("ix_inventory_mapping_shopify_location_id", table_name="inventory_mapping")
    op.drop_index("ix_inventory_mapping_shopify_inventory_item_id", table_name="inventory_mapping")
    op.drop_index("ix_inventory_mapping_external_branch_id", table_name="inventory_mapping")
    op.drop_index("ix_inventory_mapping_external_variant_id", table_name="inventory_mapping")
    op.drop_index("ix_inventory_mapping_external_product_id", table_name="inventory_mapping")
    op.drop_index("ix_inventory_mapping_sync_status", table_name="inventory_mapping")
    op.drop_table("inventory_mapping")
    op.drop_index("ix_customer_mapping_phone", table_name="customer_mapping")
    op.drop_index("ix_customer_mapping_email", table_name="customer_mapping")
    op.drop_index("ix_customer_mapping_shopify_customer_id", table_name="customer_mapping")
    op.drop_index("ix_customer_mapping_external_customer_id", table_name="customer_mapping")
    op.drop_index("ix_customer_mapping_sync_status", table_name="customer_mapping")
    op.drop_table("customer_mapping")
    op.drop_index("ix_order_mapping_external_invoice_id", table_name="order_mapping")
    op.drop_index("ix_order_mapping_shopify_order_id", table_name="order_mapping")
    op.drop_index("ix_order_mapping_external_order_id", table_name="order_mapping")
    op.drop_index("ix_order_mapping_sync_status", table_name="order_mapping")
    op.drop_table("order_mapping")
    op.drop_index("ix_variant_mapping_sku", table_name="variant_mapping")
    op.drop_index("ix_variant_mapping_shopify_inventory_item_id", table_name="variant_mapping")
    op.drop_index("ix_variant_mapping_shopify_variant_id", table_name="variant_mapping")
    op.drop_index("ix_variant_mapping_shopify_product_id", table_name="variant_mapping")
    op.drop_index("ix_variant_mapping_external_product_id", table_name="variant_mapping")
    op.drop_index("ix_variant_mapping_external_variant_id", table_name="variant_mapping")
    op.drop_index("ix_variant_mapping_sync_status", table_name="variant_mapping")
    op.drop_table("variant_mapping")
    op.drop_index("ix_product_mapping_sku", table_name="product_mapping")
    op.drop_index("ix_product_mapping_shopify_product_id", table_name="product_mapping")
    op.drop_index("ix_product_mapping_external_product_id", table_name="product_mapping")
    op.drop_index("ix_product_mapping_sync_status", table_name="product_mapping")
    op.drop_table("product_mapping")
