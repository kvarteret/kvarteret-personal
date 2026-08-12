"""contract legacy application groups after friend relationship reconciliation

Revision ID: 20260812_1400
Revises: 20260812_1300
Create Date: 2026-08-12 14:00:00

The downgrade recreates empty legacy tables for structural reversibility only.
It cannot reconstruct group membership truthfully after independent friend
invitations have been created; restoring a pre-contract database backup is the
data rollback strategy.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_1400"
down_revision = "20260812_1300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE unmatched_legacy bigint;
            DECLARE unmatched_friend bigint;
            BEGIN
                SELECT count(*)
                  INTO unmatched_legacy
                  FROM public.volunteer_application_group_members legacy
                 WHERE legacy.role = 'invitee'
                   AND NOT EXISTS (
                       SELECT 1
                         FROM public.volunteer_application_friend_invitations relationship
                        WHERE relationship.id = legacy.id
                   );
                IF unmatched_legacy <> 0 THEN
                    RAISE EXCEPTION
                        'Cannot remove application groups: % legacy invitee memberships are unmatched',
                        unmatched_legacy;
                END IF;

                SELECT count(*)
                  INTO unmatched_friend
                  FROM public.volunteer_application_invites invite
                 WHERE invite.source = 'friend_invite'
                   AND NOT EXISTS (
                       SELECT 1
                         FROM public.volunteer_application_friend_invitations relationship
                        WHERE relationship.invitee_application_id = invite.id
                   );
                IF unmatched_friend <> 0 THEN
                    RAISE EXCEPTION
                        'Cannot remove application groups: % friend applications are unmatched',
                        unmatched_friend;
                END IF;
            END $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE public.volunteer_application_invites
               SET source = 'friend_invite'
             WHERE source = 'group_invite'
            """
        )
    )
    op.drop_table("volunteer_application_group_members", schema="public")
    op.drop_table("volunteer_application_groups", schema="public")


def downgrade() -> None:
    op.create_table(
        "volunteer_application_groups",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="public",
    )
    op.create_table(
        "volunteer_application_group_members",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("invite_id", sa.BigInteger(), nullable=True),
        sa.Column("applicant_email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dropped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dropped_by_user_account_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["group_id"], ["public.volunteer_application_groups.id"]
        ),
        sa.ForeignKeyConstraint(
            ["invite_id"],
            ["public.volunteer_application_invites.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["dropped_by_user_account_id"],
            ["public.user_accounts.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "role in ('inviter', 'invitee')",
            name="ck_volunteer_application_group_members_role",
        ),
        sa.CheckConstraint(
            "status in ('active', 'dropped')",
            name="ck_volunteer_application_group_members_status",
        ),
        sa.UniqueConstraint(
            "group_id",
            "invite_id",
            name="uq_volunteer_application_group_members_invite",
        ),
        schema="public",
    )
