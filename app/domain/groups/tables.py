"""Tables owned by the groups module."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Table, Text

from app.db.metadata import public_metadata

groups = Table(
    "groups",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("slug", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text),
    Column("is_active", Boolean, nullable=False),
    Column("active_through_semester", Integer, nullable=False),
    Column("parent_group_id", BigInteger),
    Column("discount_tier", Integer),
    Column("created_at", DateTime(timezone=True)),
)
