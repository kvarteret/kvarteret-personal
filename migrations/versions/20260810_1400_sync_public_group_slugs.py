"""sync Personal group identifiers with published Sanity groups

Revision ID: 20260810_1400
Revises: 20260729_1300
Create Date: 2026-08-10 14:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260810_1400"
down_revision = "20260729_1300"
branch_labels = None
depends_on = None

_SLUG_CUTOVER = {
    "mannskoret-arme-riddere": "arme-riddere",
    "studentkoret-blandede-akademikere": "blandede-akademikere",
    "studinekoret-sirenene": "sirenene",
}

_MISSING_GROUPS = (
    ("Grøndahls", "grondahls", "skjenke-gruppen"),
    ("Halvtimen", "halvtimen", "skjenke-gruppen"),
    ("Kokkegruppen", "kokkegruppen", "skjenke-gruppen"),
    ("Quiz-gruppen", "quiz-gruppen", None),
)


def upgrade() -> None:
    connection = op.get_bind()

    for old_slug, new_slug in _SLUG_CUTOVER.items():
        connection.execute(
            sa.text(
                """
                UPDATE groups
                SET slug = :new_slug
                WHERE slug = :old_slug
                  AND NOT EXISTS (
                    SELECT 1 FROM groups existing WHERE existing.slug = :new_slug
                  )
                """
            ),
            {"old_slug": old_slug, "new_slug": new_slug},
        )

    for name, slug, parent_slug in _MISSING_GROUPS:
        parent_group_id = None
        if parent_slug is not None:
            parent_group_id = connection.execute(
                sa.text("SELECT id FROM groups WHERE slug = :slug"),
                {"slug": parent_slug},
            ).scalar_one_or_none()
            if parent_group_id is None:
                raise RuntimeError(f"Missing parent group for public slug {parent_slug!r}.")

        connection.execute(
            sa.text(
                """
                INSERT INTO groups (
                    name,
                    description,
                    is_active,
                    active_through_semester,
                    parent_group_id,
                    discount_tier,
                    slug
                )
                SELECT
                    :name,
                    NULL,
                    TRUE,
                    0,
                    :parent_group_id,
                    NULL,
                    :slug
                WHERE NOT EXISTS (
                    SELECT 1 FROM groups existing WHERE existing.slug = :slug
                )
                """
            ),
            {
                "name": name,
                "slug": slug,
                "parent_group_id": parent_group_id,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()

    for _name, slug, _parent_slug in reversed(_MISSING_GROUPS):
        connection.execute(
            sa.text("DELETE FROM groups WHERE slug = :slug"),
            {"slug": slug},
        )

    for old_slug, new_slug in reversed(_SLUG_CUTOVER.items()):
        connection.execute(
            sa.text("UPDATE groups SET slug = :old_slug WHERE slug = :new_slug"),
            {"old_slug": old_slug, "new_slug": new_slug},
        )
