"""seed canonical payment methods

Revision ID: 0002_payment_methods
Revises: 0001_initial
Create Date: 2026-04-29 00:00:00.000000
"""

from alembic import op

revision = "0002_payment_methods"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO payment_methods (code, display_name)
        VALUES
            ('efectivo', 'Efectivo'),
            ('transferencia', 'Transferencia')
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM payment_methods WHERE code IN ('efectivo', 'transferencia')")
