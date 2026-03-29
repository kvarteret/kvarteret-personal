"""add mobile card april state

Revision ID: 20260329_1300
Revises: 20260327_1515
Create Date: 2026-03-29 13:00:00
"""

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260329_1300"
down_revision = "20260327_1515"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mobile_card_april_state",
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_account_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by_user_account_id"],
            ["public.user_accounts.id"],
            name="fk_mobile_card_april_state_updated_by_user_account_id",
            ondelete="SET NULL",
        ),
        schema="public",
    )
    op.execute(
        sa.text(
            """
            insert into public.mobile_card_april_state (
                enabled,
                updated_at,
                updated_by_user_account_id
            ) values (
                :enabled,
                :updated_at,
                :updated_by_user_account_id
            )
            """
        ).bindparams(
            enabled=False,
            updated_at=datetime.now(UTC),
            updated_by_user_account_id=None,
        )
    )


def downgrade() -> None:
    op.drop_table("mobile_card_april_state", schema="public")
