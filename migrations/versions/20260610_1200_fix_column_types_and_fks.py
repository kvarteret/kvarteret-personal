"""add missing foreign keys after schema rename to English

Revision ID: 20260610_1200
Revises: 20260610_1100
Create Date: 2026-06-10 12:00:00

Adds foreign keys that were missing from the legacy schema:
- groups.parent_group_id -> groups.id (self-referential)
- volunteer_application_group_members.dropped_by_user_account_id -> user_accounts.id

FKs are added as NOT VALID first, then validated, to avoid locking
on potentially orphaned rows. If orphan detection is needed, add
a guard query before validation.
"""
from alembic import op

revision = "20260610_1200"
down_revision = "20260610_1100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Self-referential FK on groups
    op.execute("""
        ALTER TABLE groups
        ADD CONSTRAINT fk_groups_parent_group_id
        FOREIGN KEY (parent_group_id) REFERENCES groups(id)
        NOT VALID
    """)
    op.execute("ALTER TABLE groups VALIDATE CONSTRAINT fk_groups_parent_group_id")

    # FK on volunteer_application_group_members.dropped_by_user_account_id
    op.execute("""
        ALTER TABLE volunteer_application_group_members
        ADD CONSTRAINT fk_group_members_dropped_by_user_account_id
        FOREIGN KEY (dropped_by_user_account_id) REFERENCES user_accounts(id)
        NOT VALID
    """)
    op.execute(
        "ALTER TABLE volunteer_application_group_members "
        "VALIDATE CONSTRAINT fk_group_members_dropped_by_user_account_id"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE volunteer_application_group_members "
        "DROP CONSTRAINT IF EXISTS fk_group_members_dropped_by_user_account_id"
    )
    op.execute(
        "ALTER TABLE groups DROP CONSTRAINT IF EXISTS fk_groups_parent_group_id"
    )
