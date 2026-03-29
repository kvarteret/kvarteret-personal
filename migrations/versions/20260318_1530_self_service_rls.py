"""self-service RLS for authenticated users

Revision ID: 20260318_1530
Revises: 20260317_1030
Create Date: 2026-03-18 15:30:00
"""

from alembic import op


revision = "20260318_1530"
down_revision = "20260317_1030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.current_legacy_user_id()
        RETURNS bigint
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
          SELECT ua.legacy_user_id
          FROM public.user_accounts AS ua
          WHERE ua.auth_user_id = auth.uid()
          LIMIT 1
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.current_legacy_user_id() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.current_legacy_user_id() TO authenticated")

    op.execute("GRANT USAGE ON SCHEMA public TO authenticated")
    op.execute(
        """
        GRANT SELECT ON TABLE
          public.user_accounts,
          public.personal,
          public.personal_bilde,
          public.historie,
          public.verv,
          public.grupper
        TO authenticated
        """
    )

    for table_name in ("user_accounts", "personal", "personal_bilde", "historie", "verv", "grupper"):
        op.execute(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS user_accounts_select_self_authenticated ON public.user_accounts")
    op.execute("DROP POLICY IF EXISTS personal_select_self_authenticated ON public.personal")
    op.execute("DROP POLICY IF EXISTS personal_bilde_select_self_authenticated ON public.personal_bilde")
    op.execute("DROP POLICY IF EXISTS historie_select_self_authenticated ON public.historie")
    op.execute("DROP POLICY IF EXISTS verv_select_self_authenticated ON public.verv")
    op.execute("DROP POLICY IF EXISTS grupper_select_self_authenticated ON public.grupper")

    op.execute(
        """
        CREATE POLICY user_accounts_select_self_authenticated
        ON public.user_accounts
        FOR SELECT
        TO authenticated
        USING (auth.uid() = auth_user_id)
        """
    )
    op.execute(
        """
        CREATE POLICY personal_select_self_authenticated
        ON public.personal
        FOR SELECT
        TO authenticated
        USING (id = public.current_legacy_user_id())
        """
    )
    op.execute(
        """
        CREATE POLICY personal_bilde_select_self_authenticated
        ON public.personal_bilde
        FOR SELECT
        TO authenticated
        USING (id_personal = public.current_legacy_user_id())
        """
    )
    op.execute(
        """
        CREATE POLICY historie_select_self_authenticated
        ON public.historie
        FOR SELECT
        TO authenticated
        USING (id_personal = public.current_legacy_user_id())
        """
    )
    op.execute(
        """
        CREATE POLICY verv_select_self_authenticated
        ON public.verv
        FOR SELECT
        TO authenticated
        USING (
          EXISTS (
            SELECT 1
            FROM public.historie AS h
            WHERE h.id_verv = public.verv.id
              AND h.id_personal = public.current_legacy_user_id()
          )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY grupper_select_self_authenticated
        ON public.grupper
        FOR SELECT
        TO authenticated
        USING (
          EXISTS (
            SELECT 1
            FROM public.historie AS h
            WHERE h.id_gruppe = public.grupper.id
              AND h.id_personal = public.current_legacy_user_id()
          )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS grupper_select_self_authenticated ON public.grupper")
    op.execute("DROP POLICY IF EXISTS verv_select_self_authenticated ON public.verv")
    op.execute("DROP POLICY IF EXISTS historie_select_self_authenticated ON public.historie")
    op.execute("DROP POLICY IF EXISTS personal_bilde_select_self_authenticated ON public.personal_bilde")
    op.execute("DROP POLICY IF EXISTS personal_select_self_authenticated ON public.personal")
    op.execute("DROP POLICY IF EXISTS user_accounts_select_self_authenticated ON public.user_accounts")

    for table_name in ("grupper", "verv", "historie", "personal_bilde", "personal", "user_accounts"):
        op.execute(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY")

    op.execute(
        """
        REVOKE SELECT ON TABLE
          public.user_accounts,
          public.personal,
          public.personal_bilde,
          public.historie,
          public.verv,
          public.grupper
        FROM authenticated
        """
    )
    op.execute("REVOKE USAGE ON SCHEMA public FROM authenticated")
    op.execute("REVOKE EXECUTE ON FUNCTION public.current_legacy_user_id() FROM authenticated")
    op.execute("DROP FUNCTION IF EXISTS public.current_legacy_user_id()")
