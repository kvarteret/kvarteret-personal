"""Tables owned by the courses module."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Table, Text

from app.db.metadata import public_metadata

courses = Table(
    "courses",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", Text, nullable=False),
    Column("description", Text),
    Column("created_at", DateTime(timezone=True)),
)

course_completions = Table(
    "course_completions",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("volunteer_id", BigInteger, ForeignKey("public.volunteer_records.id"), nullable=False),
    Column("course_id", BigInteger, ForeignKey("public.courses.id"), nullable=False),
    Column("completed_semester", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True)),
)

group_course_requirements = Table(
    "group_course_requirements",
    public_metadata,
    Column("course_id", BigInteger, ForeignKey("public.courses.id"), primary_key=True),
    Column("group_id", BigInteger, ForeignKey("public.groups.id"), primary_key=True),
)
