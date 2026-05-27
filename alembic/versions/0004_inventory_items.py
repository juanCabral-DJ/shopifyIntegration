"""add inventory items

Revision ID: 0004_inventory_items
Revises: 0003_bigint_shopify_ids
Create Date: 2026-04-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_inventory_items"
down_revision = "0003_bigint_shopify_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("shopify_product_id", sa.BigInteger(), nullable=False),
        sa.Column("shopify_variant_id", sa.BigInteger(), nullable=False),
        sa.Column("inventory_item_id", sa.BigInteger(), nullable=False),
        sa.Column("location_id", sa.BigInteger(), nullable=False),
        sa.Column("sku", sa.String(length=128), nullable=True),
        sa.Column("product_title", sa.String(length=255), nullable=False),
        sa.Column("variant_title", sa.String(length=255), nullable=True),
        sa.Column("available", sa.Integer(), nullable=True),
        sa.Column("tracked", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("shopify_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("inventory_item_id", "location_id", name="uq_inventory_item_location"),
    )
    op.create_index("ix_inventory_items_shopify_product_id", "inventory_items", ["shopify_product_id"])
    op.create_index("ix_inventory_items_shopify_variant_id", "inventory_items", ["shopify_variant_id"])
    op.create_index("ix_inventory_items_inventory_item_id", "inventory_items", ["inventory_item_id"])
    op.create_index("ix_inventory_items_location_id", "inventory_items", ["location_id"])
    op.create_index("ix_inventory_items_sku", "inventory_items", ["sku"])


def downgrade() -> None:
    op.drop_index("ix_inventory_items_sku", table_name="inventory_items")
    op.drop_index("ix_inventory_items_location_id", table_name="inventory_items")
    op.drop_index("ix_inventory_items_inventory_item_id", table_name="inventory_items")
    op.drop_index("ix_inventory_items_shopify_variant_id", table_name="inventory_items")
    op.drop_index("ix_inventory_items_shopify_product_id", table_name="inventory_items")
    op.drop_table("inventory_items")
