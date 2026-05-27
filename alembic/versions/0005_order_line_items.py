"""add order items

Revision ID: 0005_order_line_items
Revises: 0004_inventory_items
Create Date: 2026-04-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_order_line_items"
down_revision = "0004_inventory_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("shopify_line_item_id", sa.BigInteger(), nullable=False),
        sa.Column("shopify_product_id", sa.BigInteger(), nullable=True),
        sa.Column("shopify_variant_id", sa.BigInteger(), nullable=True),
        sa.Column("sku", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("variant_title", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("fulfillment_status", sa.String(length=50), nullable=True),
        sa.UniqueConstraint("order_id", "shopify_line_item_id", name="uq_order_line_item"),
    )
    op.create_index("ix_order_items_shopify_product_id", "order_items", ["shopify_product_id"])
    op.create_index("ix_order_items_shopify_variant_id", "order_items", ["shopify_variant_id"])
    op.create_index("ix_order_items_sku", "order_items", ["sku"])


def downgrade() -> None:
    op.drop_index("ix_order_items_sku", table_name="order_items")
    op.drop_index("ix_order_items_shopify_variant_id", table_name="order_items")
    op.drop_index("ix_order_items_shopify_product_id", table_name="order_items")
    op.drop_table("order_items")
