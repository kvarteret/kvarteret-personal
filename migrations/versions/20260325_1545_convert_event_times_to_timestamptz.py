"""convert event times to timestamptz

Revision ID: 20260325_1545
Revises: 20260325_1300
Create Date: 2026-03-25 15:45:00
"""

from alembic import op


revision = "20260325_1545"
down_revision = "20260325_1300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
alter table public.events
    alter column event_start type timestamptz
        using timezone('Europe/Oslo', event_start),
    alter column event_end type timestamptz
        using timezone('Europe/Oslo', event_end);
"""
    )


def downgrade() -> None:
    op.execute(
        """
alter table public.events
    alter column event_start type timestamp without time zone
        using timezone('Europe/Oslo', event_start),
    alter column event_end type timestamp without time zone
        using timezone('Europe/Oslo', event_end);
"""
    )
