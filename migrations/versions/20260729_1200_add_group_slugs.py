"""add stable slugs to groups

Revision ID: 20260729_1200
Revises: 20260610_1600
Create Date: 2026-07-29 12:00:00
"""

from __future__ import annotations

import re
import unicodedata

from alembic import op
import sqlalchemy as sa

revision = "20260729_1200"
down_revision = "20260610_1600"
branch_labels = None
depends_on = None

_NORWEGIAN_TRANSLITERATION = str.maketrans(
    {
        "æ": "ae",
        "ø": "o",
        "å": "a",
        "Æ": "Ae",
        "Ø": "O",
        "Å": "A",
    }
)


def _slugify(value: str) -> str:
    transliterated = value.translate(_NORWEGIAN_TRANSLITERATION)
    ascii_value = (
        unicodedata.normalize("NFKD", transliterated)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def upgrade() -> None:
    op.add_column("groups", sa.Column("slug", sa.Text(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, name FROM groups ORDER BY id")
    ).mappings()
    used_slugs: set[str] = set()
    for row in rows:
        base_slug = _slugify(row["name"]) or f"group-{row['id']}"
        slug = base_slug
        if slug in used_slugs:
            slug = f"{base_slug}-{row['id']}"
        while slug in used_slugs:
            slug = f"{slug}-{row['id']}"
        used_slugs.add(slug)
        connection.execute(
            sa.text("UPDATE groups SET slug = :slug WHERE id = :group_id"),
            {"group_id": row["id"], "slug": slug},
        )

    op.alter_column("groups", "slug", existing_type=sa.Text(), nullable=False)
    op.create_unique_constraint("uq_groups_slug", "groups", ["slug"])


def downgrade() -> None:
    op.drop_constraint("uq_groups_slug", "groups", type_="unique")
    op.drop_column("groups", "slug")
