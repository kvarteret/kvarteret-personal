"""live people query indexes

Revision ID: 20260316_1500
Revises: 20260313_1545
Create Date: 2026-03-16 15:00:00
"""

from alembic import op


revision = "20260316_1500"
down_revision = "20260313_1545"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.idx_people_directory_mv_phone_trgm")
    op.execute("DROP INDEX IF EXISTS public.idx_people_directory_mv_email_trgm")
    op.execute("DROP INDEX IF EXISTS public.idx_people_directory_mv_last_name_trgm")
    op.execute("DROP INDEX IF EXISTS public.idx_people_directory_mv_first_name_trgm")
    op.execute("DROP INDEX IF EXISTS public.idx_people_directory_mv_full_name_trgm")
    op.execute("DROP INDEX IF EXISTS public.idx_people_directory_mv_name_sort")
    op.execute("DROP INDEX IF EXISTS public.idx_people_directory_mv_id")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS public.people_directory_mv")

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_personal_name_sort
        ON public.personal (etternavn, fornavn, id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_personal_birth_date
        ON public.personal (fodselsdato)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_historie_personal_semester_group
        ON public.historie (id_personal, semester, id_gruppe)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_historie_group_semester_id_desc
        ON public.historie (id_gruppe, semester DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_historie_kurs_personal_kurs
        ON public.historie_kurs (id_personal, id_kurs)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_historie_kurs_kurs_date_id_desc
        ON public.historie_kurs (id_kurs, gjennomfort_dato DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_personal_first_name_trgm
        ON public.personal
        USING gin ((lower(coalesce(fornavn, ''))) gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_personal_last_name_trgm
        ON public.personal
        USING gin ((lower(coalesce(etternavn, ''))) gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_personal_email_trgm
        ON public.personal
        USING gin ((lower(coalesce(epost, ''))) gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_personal_phone_trgm
        ON public.personal
        USING gin ((lower(coalesce(telefon, ''))) gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.idx_personal_phone_trgm")
    op.execute("DROP INDEX IF EXISTS public.idx_personal_email_trgm")
    op.execute("DROP INDEX IF EXISTS public.idx_personal_last_name_trgm")
    op.execute("DROP INDEX IF EXISTS public.idx_personal_first_name_trgm")
    op.execute("DROP INDEX IF EXISTS public.idx_historie_kurs_kurs_date_id_desc")
    op.execute("DROP INDEX IF EXISTS public.idx_historie_kurs_personal_kurs")
    op.execute("DROP INDEX IF EXISTS public.idx_historie_group_semester_id_desc")
    op.execute("DROP INDEX IF EXISTS public.idx_historie_personal_semester_group")
    op.execute("DROP INDEX IF EXISTS public.idx_personal_birth_date")
    op.execute("DROP INDEX IF EXISTS public.idx_personal_name_sort")
