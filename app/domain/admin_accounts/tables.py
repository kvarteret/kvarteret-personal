"""Tables owned by the auth and admin_accounts modules."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.metadata import public_metadata

_USER_ACCOUNTS_ID_FK = "public.user_accounts.id"
_GROUPS_ID_FK = "public.groups.id"

user_accounts = Table(
    "user_accounts",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("auth_user_id", UUID(as_uuid=True), nullable=False),
    Column("username", String(256), nullable=False),
    Column("email", String(320), nullable=False),
    Column("display_name", String(256)),
    Column("role", String(64), nullable=False),
    Column("last_login", DateTime(timezone=True)),
    Column("migrated_at", DateTime(timezone=True)),
    Column("onboarding_status", String(32), nullable=False),
    Column("onboarding_last_sent_at", DateTime(timezone=True)),
    Column("activated_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

group_admin_memberships = Table(
    "group_admin_memberships",
    public_metadata,
    Column("auth_user_id", UUID(as_uuid=True), primary_key=True),
    Column("group_id", BigInteger, ForeignKey(_GROUPS_ID_FK), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

web_sessions = Table(
    "web_sessions",
    public_metadata,
    Column("session_id", String(128), primary_key=True),
    Column("auth_user_id", UUID(as_uuid=True), nullable=False),
    Column("user_account_id", BigInteger, ForeignKey(_USER_ACCOUNTS_ID_FK)),
    Column("impersonator_auth_user_id", UUID(as_uuid=True)),
    Column("impersonator_user_account_id", BigInteger, ForeignKey(_USER_ACCOUNTS_ID_FK)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("ip_address", String(64)),
    Column("user_agent", Text),
)
