"""drop auth bridge vestiges: auth_migration_events table and user_accounts.legacy_user_id

Revision ID: 20260610_1300
Revises: 20260610_1200
Create Date: 2026-06-10 13:00:00
"""
from alembic import op

revision = "20260610_1300"
down_revision = "20260610_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth_migration_events")
    op.execute("ALTER TABLE user_accounts DROP COLUMN IF EXISTS legacy_user_id")


def downgrade() -> None:
    op.execute("ALTER TABLE user_accounts ADD COLUMN IF NOT EXISTS legacy_user_id BIGINT")
    op.execute("""
        CREATE TABLE IF NOT EXISTS auth_migration_events (
            id BIGINT PRIMARY KEY,
            legacy_user_id BIGINT NOT NULL,
            auth_user_id UUID,
            email VARCHAR(320),
            outcome VARCHAR(64) NOT NULL,
            details TEXT,
            created_at TIMESTAMPTZ NOT NULL
        )
    """)
