"""drop auth bridge vestiges: auth_migration_events, legacy_user_id, and legacy RLS

Removal gate waived by Martin on 2026-06-10 together with the DigitalInternkort
API: old installed app versions lose mobile-card access and Supabase direct
reads until they update.

Also drops the five volunteer self-select RLS policies and the
current_legacy_user_id() function they route through — both are dead once
legacy_user_id is gone, and leaving them would leave broken policies behind.
The auth.uid()-based user_accounts_select_self_authenticated policy is NOT
touched (it does not depend on the bridge; M9 owns its retirement).

Downgrade restores the column and table but not the policies or function
(their exact bodies live only in the production history; restoring the
bridge would be a deliberate operation, not a mechanical downgrade).

Revision ID: 20260610_1300
Revises: 20260610_1200
Create Date: 2026-06-10 13:00:00
"""
from alembic import op

revision = "20260610_1300"
down_revision = "20260610_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS grupper_select_self_authenticated ON public.groups")
    op.execute(
        "DROP POLICY IF EXISTS historie_select_self_authenticated ON public.role_assignments"
    )
    op.execute(
        "DROP POLICY IF EXISTS personal_select_self_authenticated ON public.volunteer_records"
    )
    op.execute(
        "DROP POLICY IF EXISTS personal_bilde_select_self_authenticated ON public.volunteer_photos"
    )
    op.execute(
        "DROP POLICY IF EXISTS verv_select_self_authenticated ON public.assignment_roles"
    )
    op.execute("DROP FUNCTION IF EXISTS public.current_legacy_user_id()")
    op.execute("DROP TABLE IF EXISTS auth_migration_events")
    op.execute("ALTER TABLE user_accounts DROP COLUMN IF EXISTS legacy_user_id")


def downgrade() -> None:
    op.execute("ALTER TABLE user_accounts ADD COLUMN IF NOT EXISTS legacy_user_id BIGINT")
    op.execute("""
        CREATE TABLE IF NOT EXISTS auth_migration_events (
            id BIGINT PRIMARY KEY,
            legacy_user_id BIGINT NOT NULL,
            auth_user_id UUID,
            email VARCHAR(320),
            outcome VARCHAR(64) NOT NULL,
            details TEXT,
            created_at TIMESTAMPTZ NOT NULL
        )
    """)
