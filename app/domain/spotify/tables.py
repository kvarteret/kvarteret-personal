"""Tables owned by the spotify module."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, Table, Text

from app.db.metadata import public_metadata

integration_tokens = Table(
    "integration_tokens",
    public_metadata,
    Column("provider", String(64), primary_key=True),
    Column("refresh_token", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("updated_by_user_account_id", BigInteger, ForeignKey("public.user_accounts.id")),
)
