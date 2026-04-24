"""add taxonomy groups to event types

Revision ID: 20260422_1600
Revises: 20260409_1700
Create Date: 2026-04-22 16:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260422_1600"
down_revision = "20260409_1700"
branch_labels = None
depends_on = None


EVENT_TYPE_TAXONOMY_GROUPS = {
    "aapen-oving": "Musikk",
    "konsert": "Musikk",
    "festival": "Musikk",
    "forestilling": "Scenekunst",
    "revy": "Scenekunst",
    "debatt": "Faglig",
    "panelsamtale": "Faglig",
    "foredrag": "Faglig",
    "frokostmote": "Faglig",
    "sosialt": "Sosialt",
    "quiz": "Sosialt",
    "marked": "Sosialt",
    "film-kino": "Sosialt",
    "programslipp": "Sosialt",
    "infomote": "Organisasjon",
    "generalforsamling": "Organisasjon",
    "apningsmote": "Organisasjon",
}


def upgrade() -> None:
    op.add_column("event_types", sa.Column("taxonomy_group", sa.Text(), nullable=True), schema="public")

    connection = op.get_bind()
    for slug, taxonomy_group in EVENT_TYPE_TAXONOMY_GROUPS.items():
        connection.execute(
            sa.text(
                """
                update public.event_types
                set taxonomy_group = :taxonomy_group,
                    updated_at = timezone('utc', now())
                where slug = :slug
                """
            ),
            {"slug": slug, "taxonomy_group": taxonomy_group},
        )

    connection.execute(
        sa.text(
            """
            update public.event_types
            set taxonomy_group = 'Annet',
                updated_at = timezone('utc', now())
            where taxonomy_group is null
            """
        )
    )

    op.alter_column("event_types", "taxonomy_group", schema="public", nullable=False)


def downgrade() -> None:
    op.drop_column("event_types", "taxonomy_group", schema="public")
