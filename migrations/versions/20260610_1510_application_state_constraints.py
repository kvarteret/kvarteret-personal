"""add application state check constraints

Revision ID: 20260610_1510
Revises: 20260610_1500
Create Date: 2026-06-10 15:10:00
"""
from alembic import op

revision = "20260610_1510"
down_revision = "20260610_1500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE volunteer_application_invites
        ADD CONSTRAINT ck_application_status
        CHECK (status IN ('prospect', 'invited', 'submitted', 'promoted', 'rejected'))
        NOT VALID
    """)
    op.execute(
        "ALTER TABLE volunteer_application_invites "
        "VALIDATE CONSTRAINT ck_application_status"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE volunteer_application_invites "
        "DROP CONSTRAINT IF EXISTS ck_application_status"
    )
