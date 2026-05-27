"""use bigint for shopify ids

Revision ID: 0003_bigint_shopify_ids
Revises: 0002_payment_methods
Create Date: 2026-04-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_bigint_shopify_ids"
down_revision = "0002_payment_methods"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("customers", "shopify_customer_id", existing_type=sa.Integer(), type_=sa.BigInteger())
    op.alter_column("orders", "shopify_order_id", existing_type=sa.Integer(), type_=sa.BigInteger())


def downgrade() -> None:
    op.alter_column("orders", "shopify_order_id", existing_type=sa.BigInteger(), type_=sa.Integer())
    op.alter_column("customers", "shopify_customer_id", existing_type=sa.BigInteger(), type_=sa.Integer())
