"""drop arbeidsstatus columns

Revision ID: 20260319_2145
Revises: 20260319_1430
Create Date: 2026-03-19 21:45:00
"""

from alembic import op


revision = "20260319_2145"
down_revision = "20260319_1430"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("nytt_personal", "arb_status")
    op.drop_column("personal", "arb_status")


def downgrade() -> None:
    raise RuntimeError("Downgrade is not supported for dropped arbeidsstatus columns.")
