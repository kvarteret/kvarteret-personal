"""extract mobile_card access codes into their own table

Revision ID: 20260610_1400
Revises: 20260610_1300
Create Date: 2026-06-10 14:00:00

Creates ``mobile_card_access_codes`` (volunteer_id PK/FK, code_hash, created_at)
and drops the legacy token columns from ``volunteer_records``. Existing codes
are deliberately NOT copied: they are plaintext and minutes-lived, and the new
column stores only HMAC digests. In-flight codes die at cutover; volunteers
request a new one.
"""
from alembic import op

revision = "20260610_1400"
down_revision = "20260610_1300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE mobile_card_access_codes (
            volunteer_id BIGINT PRIMARY KEY
                REFERENCES volunteer_records(id),
            code_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
    """)
    op.execute("ALTER TABLE volunteer_records DROP COLUMN IF EXISTS internkortaccesstoken")
    op.execute(
        "ALTER TABLE volunteer_records DROP COLUMN IF EXISTS internkort_access_token_created_at"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE volunteer_records ADD COLUMN IF NOT EXISTS internkortaccesstoken TEXT"
    )
    op.execute(
        "ALTER TABLE volunteer_records ADD COLUMN IF NOT EXISTS internkort_access_token_created_at TIMESTAMPTZ"
    )
    op.execute("DROP TABLE IF EXISTS mobile_card_access_codes")
