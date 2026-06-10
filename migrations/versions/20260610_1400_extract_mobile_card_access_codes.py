"""extract mobile_card access codes into their own table

Revision ID: 20260610_1400
Revises: 20260610_1300
Create Date: 2026-06-10 14:00:00

Creates ``mobile_card_access_codes`` (volunteer_id PK/FK, code_hash, created_at)
and copies existing plaintext codes from ``volunteer_records``.  The column is
named ``code_hash`` because M8 will hash the values; for now they are stored
as plaintext (M8 finishes the hashing).
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
    op.execute("""
        INSERT INTO mobile_card_access_codes (volunteer_id, code_hash, created_at)
        SELECT id, internkortaccesstoken,
               COALESCE(internkort_access_token_created_at, created_at)
        FROM volunteer_records
        WHERE internkortaccesstoken IS NOT NULL
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
    op.execute("""
        UPDATE volunteer_records
        SET internkortaccesstoken = mac.code_hash,
            internkort_access_token_created_at = mac.created_at
        FROM mobile_card_access_codes mac
        WHERE volunteer_records.id = mac.volunteer_id
    """)
    op.execute("DROP TABLE IF EXISTS mobile_card_access_codes")
