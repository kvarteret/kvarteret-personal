"""initial auth support tables

Revision ID: 20260313_1015
Revises: 20260313_0900
Create Date: 2026-03-13 10:15:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260313_1015"
down_revision = "20260313_0900"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_accounts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("auth_user_id", sa.UUID(), nullable=False, unique=True),
        sa.Column("legacy_user_id", sa.BigInteger(), nullable=True, unique=True),
        sa.Column("username", sa.String(length=256), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=True),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migrated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_user_accounts_email", "user_accounts", ["email"])
    op.create_index("ix_user_accounts_username", "user_accounts", ["username"])

    op.create_table(
        "group_admin_memberships",
        sa.Column("auth_user_id", sa.UUID(), nullable=False),
        sa.Column("gruppe_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["gruppe_id"], ["grupper.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("auth_user_id", "gruppe_id"),
    )

    op.create_table(
        "web_sessions",
        sa.Column("session_id", sa.String(length=128), primary_key=True),
        sa.Column("auth_user_id", sa.UUID(), nullable=False),
        sa.Column("user_account_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_accounts.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "auth_migration_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("legacy_user_id", sa.BigInteger(), nullable=False),
        sa.Column("auth_user_id", sa.UUID(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("auth_migration_events")
    op.drop_table("web_sessions")
    op.drop_table("group_admin_memberships")
    op.drop_index("ix_user_accounts_username", table_name="user_accounts")
    op.drop_index("ix_user_accounts_email", table_name="user_accounts")
    op.drop_table("user_accounts")
