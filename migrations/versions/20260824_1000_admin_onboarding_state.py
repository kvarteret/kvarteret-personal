"""track admin onboarding state

Revision ID: 20260824_1000
Revises: 20260824_0900
Create Date: 2026-08-24 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260824_1000"
down_revision = "20260824_0900"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_accounts",
        sa.Column(
            "onboarding_status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
        schema="public",
    )
    op.add_column(
        "user_accounts",
        sa.Column("onboarding_last_sent_at", sa.DateTime(timezone=True)),
        schema="public",
    )
    op.add_column(
        "user_accounts",
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("user_accounts", "activated_at", schema="public")
    op.drop_column("user_accounts", "onboarding_last_sent_at", schema="public")
    op.drop_column("user_accounts", "onboarding_status", schema="public")
