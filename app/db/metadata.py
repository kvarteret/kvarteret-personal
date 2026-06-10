"""Shared SQLAlchemy MetaData for the ``public`` schema.

All domain module table definitions bind their ``Table`` objects
to this single ``MetaData`` instance so that Alembic autogeneration
and cross-module read joins work unchanged.
"""

from sqlalchemy import MetaData

public_metadata = MetaData(schema="public")
