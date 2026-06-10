"""add rate_limits table for database-backed rate limiting

Revision ID: 20260610_1600
Revises: 20260610_1510
Create Date: 2026-06-10 16:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20260610_1600"
down_revision = "20260610_1510"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limits",
        sa.Column("key", sa.String(256), primary_key=True),
        sa.Column("last_used", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.BigInteger, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("rate_limits")
