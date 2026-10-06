"""Aggregate-only warehouse export; never stores volunteer identifiers."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Table, Text

from app.db.metadata import public_metadata

warehouse_volunteer_counts = Table(
    "warehouse_volunteer_counts",
    public_metadata,
    Column("metric", Text, primary_key=True),
    Column("semester", Integer, primary_key=True),
    Column("scope_key", Text, primary_key=True),
    Column("group_id", BigInteger),
    Column("volunteer_count", BigInteger),
    Column("is_suppressed", Boolean, nullable=False),
    Column("refreshed_at", DateTime(timezone=True), nullable=False),
)
