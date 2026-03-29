"""revoke broad public schema grants from anon and authenticated

Revision ID: 20260318_1915
Revises: 20260318_1715
Create Date: 2026-03-18 19:15:00
"""

from alembic import op


revision = "20260318_1915"
down_revision = "20260318_1715"
branch_labels = None
depends_on = None


SELF_SERVICE_TABLES = """
  public.user_accounts,
  public.personal,
  public.personal_bilde,
  public.historie,
  public.verv,
  public.grupper
"""


def upgrade() -> None:
    op.execute("REVOKE USAGE ON SCHEMA public FROM anon")
    op.execute("REVOKE USAGE ON SCHEMA public FROM authenticated")
    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM anon")
    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM authenticated")
    op.execute("REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anon")
    op.execute("REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM authenticated")
    op.execute("REVOKE ALL ON FUNCTION public.current_legacy_user_id() FROM anon")
    op.execute("REVOKE ALL ON FUNCTION public.current_legacy_user_id() FROM authenticated")

    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM authenticated")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM authenticated")

    op.execute("GRANT USAGE ON SCHEMA public TO authenticated")
    op.execute(f"GRANT SELECT ON TABLE {SELF_SERVICE_TABLES} TO authenticated")
    op.execute("GRANT EXECUTE ON FUNCTION public.current_legacy_user_id() TO authenticated")


def downgrade() -> None:
    op.execute("GRANT USAGE ON SCHEMA public TO anon")
    op.execute("GRANT USAGE ON SCHEMA public TO authenticated")
    op.execute("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO anon")
    op.execute("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO authenticated")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anon")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated")
    op.execute("GRANT EXECUTE ON FUNCTION public.current_legacy_user_id() TO authenticated")
