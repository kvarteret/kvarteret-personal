"""Bounded, pseudonymous event enthusiasm responses; no event content."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    SmallInteger,
    String,
    Table,
    Text,
    text,
)

from app.db.metadata import public_metadata

event_interest = Table(
    "event_interest",
    public_metadata,
    Column("event_id", Text, primary_key=True),
    Column("source_hash", String(64), primary_key=True),
    Column("taps", SmallInteger, nullable=False),
    Column(
        "expires_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now() + interval '90 days'"),
    ),
    CheckConstraint("taps BETWEEN 1 AND 12", name="event_interest_taps_bounds"),
    CheckConstraint(
        "source_hash ~ '^[a-f0-9]{64}$'", name="event_interest_source_hash_format"
    ),
)
Index("event_interest_expiry_idx", event_interest.c.expires_at)
