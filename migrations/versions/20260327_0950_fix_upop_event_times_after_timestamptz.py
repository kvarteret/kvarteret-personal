"""fix upop event times after timestamptz migration

Revision ID: 20260327_0950
Revises: 20260325_1545
Create Date: 2026-03-27 09:50:00
"""

from alembic import op


revision = "20260327_0950"
down_revision = "20260325_1545"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
update public.events as events
set event_start = fixes.event_start_local at time zone 'Europe/Oslo',
    event_end = fixes.event_end_local at time zone 'Europe/Oslo',
    updated_at = timezone('utc', now())
from (
    values
        ('dyrs-foelelser-2', timestamp '2026-04-07 18:00:00', timestamp '2026-04-07 20:00:00'),
        ('mannlig-prevensjon-p-piller-for-menn', timestamp '2026-04-14 18:00:00', timestamp '2026-04-14 20:00:00'),
        ('transpersoner', timestamp '2026-04-21 18:00:00', timestamp '2026-04-21 20:00:00'),
        ('edens-hage-i-bergen-tur-til-arboretet', timestamp '2026-04-28 18:00:00', timestamp '2026-04-28 20:00:00'),
        ('incels', timestamp '2026-05-05 18:00:00', timestamp '2026-05-05 20:00:00')
) as fixes(slug, event_start_local, event_end_local)
where events.slug = fixes.slug;
"""
    )


def downgrade() -> None:
    op.execute(
        """
update public.events as events
set event_start = fixes.event_start_local at time zone 'Europe/Oslo',
    event_end = fixes.event_end_local at time zone 'Europe/Oslo',
    updated_at = timezone('utc', now())
from (
    values
        ('dyrs-foelelser-2', timestamp '2026-04-07 16:00:00', timestamp '2026-04-07 18:00:00'),
        ('mannlig-prevensjon-p-piller-for-menn', timestamp '2026-04-14 16:00:00', timestamp '2026-04-14 18:00:00'),
        ('transpersoner', timestamp '2026-04-21 16:00:00', timestamp '2026-04-21 18:00:00'),
        ('edens-hage-i-bergen-tur-til-arboretet', timestamp '2026-04-28 16:00:00', timestamp '2026-04-28 18:00:00'),
        ('incels', timestamp '2026-05-05 16:00:00', timestamp '2026-05-05 18:00:00')
) as fixes(slug, event_start_local, event_end_local)
where events.slug = fixes.slug;
"""
    )
