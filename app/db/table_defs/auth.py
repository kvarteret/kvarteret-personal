from __future__ import annotations

from sqlalchemy import BigInteger, Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import UUID

auth_metadata = MetaData(schema="auth")

auth_users = Table(
    "users",
    auth_metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("email", String(320)),
)

auth_refresh_tokens = Table(
    "refresh_tokens",
    auth_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("user_id", String(255), nullable=False),
)

auth_sessions = Table(
    "sessions",
    auth_metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("user_id", UUID(as_uuid=True), nullable=False),
)

auth_identities = Table(
    "identities",
    auth_metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("user_id", UUID(as_uuid=True), nullable=False),
)
