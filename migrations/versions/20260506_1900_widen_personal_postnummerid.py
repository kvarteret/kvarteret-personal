"""widen personal.postnummerid from varchar(10) to text

The column was limited to 10 characters, but submissions can include the
city name alongside the postal code (e.g. "5011 Bergen"), which exceeds
that limit and caused the approval flow to fail with a DB error.

Revision ID: 20260506_1900
Revises: 20260422_1600
Create Date: 2026-05-06 19:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260506_1900"
down_revision = "20260422_1600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "personal",
        "postnummerid",
        type_=sa.Text(),
        existing_type=sa.String(10),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "personal",
        "postnummerid",
        type_=sa.String(10),
        existing_type=sa.Text(),
        existing_nullable=True,
    )
