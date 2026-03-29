from __future__ import annotations

from sqlalchemy import Column, DateTime, MetaData, Table, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID

storage_metadata = MetaData(schema="storage")

storage_objects = Table(
    "objects",
    storage_metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("bucket_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("owner", UUID(as_uuid=True)),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
    Column("last_accessed_at", DateTime(timezone=True)),
    Column("metadata", Text),
    Column("path_tokens", ARRAY(Text)),
    Column("version", Text),
)
