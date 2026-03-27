"""fix additional event times from descriptions

Revision ID: 20260327_1030
Revises: 20260327_0950
Create Date: 2026-03-27 10:30:00
"""

from alembic import op


revision = "20260327_1030"
down_revision = "20260327_0950"
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
        ('sexkjoepsloven-ny-innpakning-gammel-problematikk-2', timestamp '2026-03-05 18:00:00', timestamp '2026-03-05 19:00:00'),
        ('band-og-broel-konsert-med-medisinerrevybandet', timestamp '2026-03-06 20:45:00', timestamp '2026-03-06 23:00:00'),
        ('havets-apotek', timestamp '2026-03-10 18:00:00', timestamp '2026-03-10 20:00:00'),
        ('partiterapi-venstre', timestamp '2026-03-19 18:00:00', timestamp '2026-03-19 19:00:00'),
        ('kampen-mot-hjerneraaten', timestamp '2026-04-16 18:30:00', timestamp '2026-04-16 19:30:00'),
        ('spise-de-rike', timestamp '2026-04-30 18:00:00', timestamp '2026-04-30 19:00:00')
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
        ('sexkjoepsloven-ny-innpakning-gammel-problematikk-2', timestamp '2026-03-05 17:00:00', timestamp '2026-03-05 18:00:00'),
        ('band-og-broel-konsert-med-medisinerrevybandet', timestamp '2026-03-06 19:45:00', timestamp '2026-03-06 22:00:00'),
        ('havets-apotek', timestamp '2026-03-10 17:00:00', timestamp '2026-03-10 19:00:00'),
        ('partiterapi-venstre', timestamp '2026-03-19 17:00:00', timestamp '2026-03-19 18:00:00'),
        ('kampen-mot-hjerneraaten', timestamp '2026-04-16 14:00:00', timestamp '2026-04-16 15:00:00'),
        ('spise-de-rike', timestamp '2026-04-30 16:00:00', timestamp '2026-04-30 17:00:00')
) as fixes(slug, event_start_local, event_end_local)
where events.slug = fixes.slug;
"""
    )
