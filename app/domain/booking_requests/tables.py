from sqlalchemy import Column, DateTime, String, Table, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.metadata import public_metadata

booking_requests = Table(
    "booking_requests",
    public_metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("submission_id", UUID(as_uuid=True), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("snapshot", JSONB, nullable=False),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    UniqueConstraint(
        "submission_id", "content_hash", name="booking_requests_submission_content_key"
    ),
)
