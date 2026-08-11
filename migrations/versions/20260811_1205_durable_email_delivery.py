"""add durable email delivery and trace correlation

Revision ID: 20260811_1205
Revises: 20260811_1200
Create Date: 2026-08-11 12:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260811_1205"
down_revision = "20260811_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "volunteer_application_invites",
        sa.Column("origin_trace_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "domain_events",
        sa.Column("trace_id", sa.Text(), nullable=True),
    )
    op.create_table(
        "email_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_key", sa.Text(), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("recipient_email", sa.Text(), nullable=False),
        sa.Column("business_type", sa.Text(), nullable=False),
        sa.Column("business_id", sa.Text(), nullable=False),
        sa.Column("source_domain_event_id", sa.BigInteger(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "automatic_attempt_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_category", sa.Text(), nullable=True),
        sa.Column("encrypted_context", sa.LargeBinary(), nullable=True),
        sa.Column("enqueued_trace_id", sa.Text(), nullable=True),
        sa.Column("registration_id", sa.BigInteger(), nullable=True),
        sa.Column("supersedes_delivery_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('pending', 'sent', 'failed', 'expired', 'cancelled')",
            name="ck_email_deliveries_status",
        ),
        sa.ForeignKeyConstraint(
            ["registration_id"],
            ["public.volunteer_application_invites.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_domain_event_id"],
            ["public.domain_events.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_delivery_id"],
            ["public.email_deliveries.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_email_deliveries_idempotency_key"
        ),
        schema="public",
    )
    op.create_index(
        "ix_email_deliveries_due",
        "email_deliveries",
        ["status", "next_attempt_at", "lease_until"],
        schema="public",
    )
    op.create_index(
        "ix_email_deliveries_registration_id",
        "email_deliveries",
        ["registration_id"],
        schema="public",
    )
    op.create_table(
        "email_delivery_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("delivery_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("error_category", sa.Text(), nullable=True),
        sa.Column("smtp_status", sa.Integer(), nullable=True),
        sa.Column("smtp_status_class", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "stage in ('prepare', 'render', 'smtp')",
            name="ck_email_delivery_attempts_stage",
        ),
        sa.CheckConstraint(
            "outcome in ('started', 'succeeded', 'retryable_failure', 'permanent_failure', 'interrupted')",
            name="ck_email_delivery_attempts_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["delivery_id"], ["public.email_deliveries.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "delivery_id",
            "attempt_no",
            name="uq_email_delivery_attempts_delivery_attempt",
        ),
        schema="public",
    )
    op.create_index(
        "ix_email_delivery_attempts_delivery_id",
        "email_delivery_attempts",
        ["delivery_id"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_delivery_attempts_delivery_id",
        table_name="email_delivery_attempts",
        schema="public",
    )
    op.drop_table("email_delivery_attempts", schema="public")
    op.drop_index(
        "ix_email_deliveries_registration_id",
        table_name="email_deliveries",
        schema="public",
    )
    op.drop_index(
        "ix_email_deliveries_due",
        table_name="email_deliveries",
        schema="public",
    )
    op.drop_table("email_deliveries", schema="public")
    op.drop_column("domain_events", "trace_id")
    op.drop_column("volunteer_application_invites", "origin_trace_id")
