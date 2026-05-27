"""align middleware schema with SE contract v1.4

Revision ID: 0007_align_se_contract_v14
Revises: 0006_integration
Create Date: 2026-05-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_align_se_contract_v14"
down_revision = "0006_integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'map_sku_variant' AND column_name = 'invtim_codigo'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'map_sku_variant' AND column_name = 'invitm_codigo'
            ) THEN
                ALTER TABLE map_sku_variant RENAME COLUMN invtim_codigo TO invitm_codigo;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'stg_inventory_snapshots' AND column_name = 'invtim_codigo'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'stg_inventory_snapshots' AND column_name = 'invitm_codigo'
            ) THEN
                ALTER TABLE stg_inventory_snapshots RENAME COLUMN invtim_codigo TO invitm_codigo;
            END IF;
        END $$;
        """
    )
    op.alter_column("map_sucursales_locations", "shopify_location_id", existing_type=sa.BigInteger(), nullable=True)
    op.create_table(
        "map_familias_collections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("se_familia_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("se_familia_nombre", sa.String(length=255), nullable=True),
        sa.Column("shopify_collection_id", sa.BigInteger(), nullable=True, unique=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "map_marcas_tags",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("se_marca_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("se_marca_nombre", sa.String(length=255), nullable=True),
        sa.Column("shopify_tag", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("map_marcas_tags")
    op.drop_table("map_familias_collections")
    op.alter_column("map_sucursales_locations", "shopify_location_id", existing_type=sa.BigInteger(), nullable=False)
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'map_sku_variant' AND column_name = 'invitm_codigo'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'map_sku_variant' AND column_name = 'invtim_codigo'
            ) THEN
                ALTER TABLE map_sku_variant RENAME COLUMN invitm_codigo TO invtim_codigo;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'stg_inventory_snapshots' AND column_name = 'invitm_codigo'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'stg_inventory_snapshots' AND column_name = 'invtim_codigo'
            ) THEN
                ALTER TABLE stg_inventory_snapshots RENAME COLUMN invitm_codigo TO invtim_codigo;
            END IF;
        END $$;
        """
    )
