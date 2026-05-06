"""add check constraint on nytt_personal.postnummerid for 4-digit postal codes

Normalizes the one known dirty value ("5011 Bergen" → "5011") in nytt_personal,
then adds a CHECK constraint so only 4-digit codes are accepted going forward.

The personal table is left unconstrained due to extensive legacy dirty data.

Revision ID: 20260506_2000
Revises: 20260506_1900
Create Date: 2026-05-06 20:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260506_2000"
down_revision = "20260506_1900"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE nytt_personal SET postnummerid = REGEXP_REPLACE(postnummerid, '^(\\d{4}).*', '\\1')"
            " WHERE postnummerid IS NOT NULL AND postnummerid !~ '^\\d{4}$'"
        )
    )
    op.create_check_constraint(
        "ck_nytt_personal_postnummerid_format",
        "nytt_personal",
        "postnummerid IS NULL OR postnummerid ~ '^\\d{4}$'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_nytt_personal_postnummerid_format", "nytt_personal")
