"""align public group slugs with the Sanity hard cutover

Revision ID: 20260729_1300
Revises: 20260729_1200
Create Date: 2026-07-29 13:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260729_1300"
down_revision = "20260729_1200"
branch_labels = None
depends_on = None

_SLUG_CUTOVER = {
    "finans": "finans-departementet",
    "pr-etaten": "kommunikasjons-avdelingen",
    "skjenkegruppen": "skjenke-gruppen",
}


def upgrade() -> None:
    connection = op.get_bind()
    for old_slug, new_slug in _SLUG_CUTOVER.items():
        connection.execute(
            sa.text("UPDATE groups SET slug = :new_slug WHERE slug = :old_slug"),
            {"old_slug": old_slug, "new_slug": new_slug},
        )


def downgrade() -> None:
    connection = op.get_bind()
    for old_slug, new_slug in _SLUG_CUTOVER.items():
        connection.execute(
            sa.text("UPDATE groups SET slug = :old_slug WHERE slug = :new_slug"),
            {"old_slug": old_slug, "new_slug": new_slug},
        )
