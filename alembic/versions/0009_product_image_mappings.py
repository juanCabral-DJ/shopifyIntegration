"""add product image mappings

Revision ID: 0009_product_image_mappings
Revises: 0008_canonical_mappings
Create Date: 2026-06-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_product_image_mappings"
down_revision = "0008_canonical_mappings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_product_images",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("external_image_id", sa.String(length=255), nullable=False),
        sa.Column("invitm_codigo", sa.Integer(), nullable=False),
        sa.Column("admimg_linea", sa.Integer(), nullable=True),
        sa.Column("image_hash", sa.String(length=64), nullable=False),
        sa.Column("shopify_product_id", sa.BigInteger(), nullable=False),
        sa.Column("shopify_image_id", sa.BigInteger(), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("external_image_id", name="uq_map_product_images_external_image_id"),
        sa.UniqueConstraint("invitm_codigo", "image_hash", name="uq_map_product_images_item_hash"),
        sa.UniqueConstraint("shopify_image_id", name="uq_map_product_images_shopify_image_id"),
    )
    op.create_index("ix_map_product_images_external_image_id", "map_product_images", ["external_image_id"])
    op.create_index("ix_map_product_images_invitm_codigo", "map_product_images", ["invitm_codigo"])
    op.create_index("ix_map_product_images_image_hash", "map_product_images", ["image_hash"])
    op.create_index("ix_map_product_images_shopify_product_id", "map_product_images", ["shopify_product_id"])
    op.create_index("ix_map_product_images_shopify_image_id", "map_product_images", ["shopify_image_id"])


def downgrade() -> None:
    op.drop_index("ix_map_product_images_shopify_image_id", table_name="map_product_images")
    op.drop_index("ix_map_product_images_shopify_product_id", table_name="map_product_images")
    op.drop_index("ix_map_product_images_image_hash", table_name="map_product_images")
    op.drop_index("ix_map_product_images_invitm_codigo", table_name="map_product_images")
    op.drop_index("ix_map_product_images_external_image_id", table_name="map_product_images")
    op.drop_table("map_product_images")
