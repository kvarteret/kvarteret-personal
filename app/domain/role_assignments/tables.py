"""Tables owned by the role_assignments module."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, Table, Text

from app.db.metadata import public_metadata

assignment_roles = Table(
    "assignment_roles",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", Text),
    Column("group_id", BigInteger, ForeignKey("public.groups.id"), nullable=False),
    Column("penguin_points", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True)),
)

role_assignments = Table(
    "role_assignments",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("volunteer_id", BigInteger, ForeignKey("public.volunteer_records.id"), nullable=False),
    Column("group_id", BigInteger, ForeignKey("public.groups.id"), nullable=False),
    Column("role_id", BigInteger, ForeignKey("public.assignment_roles.id")),
    Column("semester", Integer, nullable=False),
    Column("contract_signed", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True)),
)
