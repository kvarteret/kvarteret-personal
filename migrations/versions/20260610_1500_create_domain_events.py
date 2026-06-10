"""add domain_events append-only audit table

Revision ID: 20260610_1500
Revises: 20260610_1400
Create Date: 2026-06-10 15:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260610_1500"
down_revision = "20260610_1400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domain_events",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("actor_user_account_id", sa.BigInteger, nullable=True),
        sa.Column("subject_type", sa.Text, nullable=False),
        sa.Column("subject_id", sa.BigInteger, nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("domain_events")
