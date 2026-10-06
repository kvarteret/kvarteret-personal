"""Add an aggregate-only volunteer count export for PostHog.

Revision ID: 20261006_1200
Revises: 20261001_1500
"""

from alembic import op
import sqlalchemy as sa

revision = "20261006_1200"
down_revision = "20261001_1500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouse_volunteer_counts",
        sa.Column("semester", sa.Integer(), primary_key=True),
        sa.Column("scope_key", sa.Text(), primary_key=True),
        sa.Column("group_id", sa.BigInteger()),
        sa.Column("volunteer_count", sa.BigInteger()),
        sa.Column("is_suppressed", sa.Boolean(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        schema="public",
    )
    op.execute("ALTER TABLE public.warehouse_volunteer_counts ENABLE ROW LEVEL SECURITY")
    op.execute(
        "REVOKE ALL ON public.warehouse_volunteer_counts "
        "FROM PUBLIC, anon, authenticated"
    )


def downgrade() -> None:
    op.drop_table("warehouse_volunteer_counts", schema="public")
