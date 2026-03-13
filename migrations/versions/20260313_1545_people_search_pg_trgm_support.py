"""people search pg_trgm support

Revision ID: 20260313_1545
Revises: 20260313_1945
Create Date: 2026-03-13 15:45:00
"""

from alembic import op


revision = "20260313_1545"
down_revision = "20260313_1945"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_personal_full_name_trgm
        ON public.personal
        USING gin ((lower(btrim(coalesce(fornavn, '') || ' ' || coalesce(etternavn, '')))) gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.idx_personal_full_name_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
