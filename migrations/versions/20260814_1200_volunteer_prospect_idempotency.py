"""add durable volunteer prospect idempotency records

Revision ID: 20260814_1200
Revises: 20260812_1400
Create Date: 2026-08-14 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_1200"
down_revision = "20260812_1400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "volunteer_prospect_idempotency_keys",
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("idempotency_key"),
        schema="public",
    )
    op.create_table(
        "volunteer_prospect_submissions",
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("registration_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('processing', 'completed')",
            name="ck_volunteer_prospect_submissions_status",
        ),
        sa.ForeignKeyConstraint(
            ["registration_id"],
            ["public.volunteer_application_invites.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("request_hash"),
        sa.UniqueConstraint("registration_id"),
        schema="public",
    )


def downgrade() -> None:
    op.drop_table("volunteer_prospect_submissions", schema="public")
    op.drop_table("volunteer_prospect_idempotency_keys", schema="public")
