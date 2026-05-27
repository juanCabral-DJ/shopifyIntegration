"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-04-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("shopify_customer_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "payment_methods",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("code", sa.String(length=100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=150), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("shopify_order_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("financial_status", sa.String(length=50), nullable=False),
        sa.Column("fulfillment_status", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="open"),
        sa.Column("is_offline_payment", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("payment_method_id", sa.Integer(), sa.ForeignKey("payment_methods.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
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
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("payment_method_id", sa.Integer(), sa.ForeignKey("payment_methods.id"), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("shopify_transaction_id", sa.String(length=128), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
    op.drop_table("payments")
    op.drop_index("ix_order_items_sku", table_name="order_items")
    op.drop_index("ix_order_items_shopify_variant_id", table_name="order_items")
    op.drop_index("ix_order_items_shopify_product_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("payment_methods")
    op.drop_table("customers")
