"""normalize room name casing

Revision ID: 20260327_1515
Revises: 20260327_1400
Create Date: 2026-03-27 15:15:00
"""

from alembic import op


revision = "20260327_1515"
down_revision = "20260327_1400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
update public.rooms as rooms
set name = fixes.name,
    updated_at = timezone('utc', now())
from (
    values
        ('teglverket', 'Teglverket'),
        ('tivoli', 'Tivoli'),
        ('storelogen', 'Storelogen'),
        ('speilsalen', 'Speilsalen'),
        ('maos', 'Maos'),
        ('stillhet', 'Stillhet'),
        ('stoy', 'Støy'),
        ('grondahls', 'Grøndahls'),
        ('halvtimen', 'Halvtimen'),
        ('stjernesalen', 'Stjernesalen')
) as fixes(slug, name)
where rooms.slug = fixes.slug;
"""
    )


def downgrade() -> None:
    op.execute(
        """
update public.rooms as rooms
set name = fixes.name,
    updated_at = timezone('utc', now())
from (
    values
        ('teglverket', 'TEGLVERKET'),
        ('tivoli', 'TIVOLI'),
        ('storelogen', 'STORELOGEN'),
        ('speilsalen', 'SPEILSALEN'),
        ('maos', 'MAOS'),
        ('stillhet', 'STILLHET'),
        ('stoy', 'STØY'),
        ('grondahls', 'GRØNDAHLS'),
        ('halvtimen', 'HALVTIMEN'),
        ('stjernesalen', 'STJERNESALEN')
) as fixes(slug, name)
where rooms.slug = fixes.slug;
"""
    )
