"""Durable email-delivery table definitions for the database metadata registry."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)

from app.db.metadata import public_metadata

email_deliveries = Table(
    "email_deliveries",
    public_metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("template_key", Text, nullable=False),
    Column("template_version", Integer, nullable=False),
    Column("recipient_email", Text, nullable=False),
    Column("business_type", Text, nullable=False),
    Column("business_id", Text, nullable=False),
    Column(
        "source_domain_event_id",
        BigInteger,
        ForeignKey("public.domain_events.id", ondelete="SET NULL"),
    ),
    Column("idempotency_key", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("automatic_attempt_count", Integer, nullable=False, server_default="0"),
    Column("next_attempt_at", DateTime(timezone=True), nullable=False),
    Column("lease_owner", Text),
    Column("lease_until", DateTime(timezone=True)),
    Column("last_error_category", Text),
    Column("encrypted_context", LargeBinary),
    Column("enqueued_trace_id", Text),
    Column(
        "registration_id",
        BigInteger,
        ForeignKey("public.volunteer_application_invites.id", ondelete="SET NULL"),
    ),
    Column(
        "supersedes_delivery_id",
        Uuid(as_uuid=True),
        ForeignKey("public.email_deliveries.id", ondelete="SET NULL"),
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("sent_at", DateTime(timezone=True)),
    CheckConstraint(
        "status in ('pending', 'sent', 'failed', 'expired', 'cancelled')",
        name="ck_email_deliveries_status",
    ),
    UniqueConstraint("idempotency_key", name="uq_email_deliveries_idempotency_key"),
)

Index(
    "ix_email_deliveries_due",
    email_deliveries.c.status,
    email_deliveries.c.next_attempt_at,
    email_deliveries.c.lease_until,
)
Index("ix_email_deliveries_registration_id", email_deliveries.c.registration_id)

email_delivery_attempts = Table(
    "email_delivery_attempts",
    public_metadata,
    Column(
        "id",
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    Column(
        "delivery_id",
        Uuid(as_uuid=True),
        ForeignKey("public.email_deliveries.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("attempt_no", Integer, nullable=False),
    Column("stage", Text, nullable=False),
    Column("outcome", Text, nullable=False),
    Column("error_category", Text),
    Column("smtp_status", Integer),
    Column("smtp_status_class", Integer),
    Column("duration_ms", Integer),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    CheckConstraint(
        "stage in ('prepare', 'render', 'smtp')",
        name="ck_email_delivery_attempts_stage",
    ),
    CheckConstraint(
        "outcome in ('started', 'succeeded', 'retryable_failure', 'permanent_failure', 'interrupted')",
        name="ck_email_delivery_attempts_outcome",
    ),
    UniqueConstraint(
        "delivery_id", "attempt_no", name="uq_email_delivery_attempts_delivery_attempt"
    ),
)

Index(
    "ix_email_delivery_attempts_delivery_id",
    email_delivery_attempts.c.delivery_id,
)
