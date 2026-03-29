"""store optional initial role assignment on volunteer registrations

Revision ID: 20260318_1715
Revises: 20260318_1530
Create Date: 2026-03-18 17:15:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260318_1715"
down_revision = "20260318_1530"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("registrering", sa.Column("initial_group_id", sa.BigInteger(), nullable=True))
    op.add_column("registrering", sa.Column("initial_role_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("registrering", "initial_role_id")
    op.drop_column("registrering", "initial_group_id")
