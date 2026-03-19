"""store shared spotify integration refresh token

Revision ID: 20260318_2015
Revises: 20260318_1915
Create Date: 2026-03-18 20:15:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260318_2015"
down_revision = "20260318_1915"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_tokens",
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_account_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by_user_account_id"],
            ["public.user_accounts.id"],
        ),
        sa.PrimaryKeyConstraint("provider"),
        schema="public",
    )


def downgrade() -> None:
    op.drop_table("integration_tokens", schema="public")
