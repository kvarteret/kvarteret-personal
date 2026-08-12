"""add pairwise friend invitation relationships and backfill legacy groups

Revision ID: 20260812_1300
Revises: 20260811_1205
Create Date: 2026-08-12 13:00:00

The legacy group tables remain in place after this revision so application
deployments can switch readers and writers independently.  The backfill is
transactional and intentionally does not emit domain events: the relationship
row preserves the original membership timestamp, while the existing event log
preserves events that actually happened at runtime.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_1300"
down_revision = "20260811_1205"
branch_labels = None
depends_on = None


_TABLE = "volunteer_application_friend_invitations"


def upgrade() -> None:
    # Fail before creating any rows when a legacy group cannot be mapped to a
    # directional relationship without guessing who invited whom.
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE malformed record;
            BEGIN
                SELECT gm.group_id, count(*) FILTER (WHERE gm.role = 'inviter') AS inviter_count
                INTO malformed
                FROM public.volunteer_application_group_members gm
                GROUP BY gm.group_id
                HAVING count(*) FILTER (WHERE gm.role = 'inviter') <> 1
                ORDER BY gm.group_id
                LIMIT 1;

                IF malformed IS NOT NULL THEN
                    RAISE EXCEPTION
                        'Cannot backfill friend invitations: legacy group % has % inviter rows; expected exactly one',
                        malformed.group_id, malformed.inviter_count;
                END IF;
            END $$;
            """
        )
    )

    op.create_table(
        _TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "inviter_application_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "invitee_application_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column("inviter_name_snapshot", sa.Text(), nullable=True),
        sa.Column("inviter_email_snapshot", sa.Text(), nullable=False),
        sa.Column("invitee_email_snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("legacy_dropped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "legacy_dropped_by_user_account_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["inviter_application_id"],
            ["public.volunteer_application_invites.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["invitee_application_id"],
            ["public.volunteer_application_invites.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["legacy_dropped_by_user_account_id"],
            ["public.user_accounts.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "invitee_application_id",
            name="uq_volunteer_application_friend_invitations_invitee",
        ),
        schema="public",
    )
    op.create_index(
        "ix_va_friend_invites_inviter_id",
        _TABLE,
        ["inviter_application_id"],
        schema="public",
    )
    op.create_index(
        "ix_va_friend_invites_invitee_id",
        _TABLE,
        ["invitee_application_id"],
        schema="public",
    )

    op.execute(
        sa.text(
            """
            INSERT INTO public.volunteer_application_friend_invitations (
                id,
                inviter_application_id,
                invitee_application_id,
                inviter_name_snapshot,
                inviter_email_snapshot,
                invitee_email_snapshot,
                created_at,
                legacy_dropped_at,
                legacy_dropped_by_user_account_id
            )
            SELECT
                invitee_membership.id,
                inviter_membership.invite_id,
                invitee_membership.invite_id,
                NULLIF(
                    trim(concat_ws(' ', inviter_submission.first_name, inviter_submission.last_name)),
                    ''
                ),
                inviter_membership.applicant_email,
                invitee_membership.applicant_email,
                invitee_membership.created_at,
                invitee_membership.dropped_at,
                invitee_membership.dropped_by_user_account_id
            FROM public.volunteer_application_group_members invitee_membership
            JOIN public.volunteer_application_group_members inviter_membership
              ON inviter_membership.group_id = invitee_membership.group_id
             AND inviter_membership.role = 'inviter'
            LEFT JOIN public.volunteer_application_submissions inviter_submission
              ON inviter_submission.invite_id = inviter_membership.invite_id
            WHERE invitee_membership.role = 'invitee'
            ORDER BY invitee_membership.id
            """
        )
    )

    op.execute(
        sa.text(
            """
            SELECT setval(
                pg_get_serial_sequence(
                    'public.volunteer_application_friend_invitations', 'id'
                ),
                COALESCE(
                    (SELECT max(id) FROM public.volunteer_application_friend_invitations),
                    0
                ) + 1,
                false
            )
            """
        )
    )

    op.execute(
        sa.text(
            """
            DO $$
            DECLARE legacy_invitee_count bigint;
            DECLARE backfilled_count bigint;
            BEGIN
                SELECT count(*)
                  INTO legacy_invitee_count
                  FROM public.volunteer_application_group_members
                 WHERE role = 'invitee';
                SELECT count(*)
                  INTO backfilled_count
                  FROM public.volunteer_application_friend_invitations;

                IF backfilled_count <> legacy_invitee_count THEN
                    RAISE EXCEPTION
                        'Friend invitation backfill count mismatch: wrote %, expected %',
                        backfilled_count, legacy_invitee_count;
                END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_va_friend_invites_invitee_id",
        table_name=_TABLE,
        schema="public",
    )
    op.drop_index(
        "ix_va_friend_invites_inviter_id",
        table_name=_TABLE,
        schema="public",
    )
    op.drop_table(_TABLE, schema="public")
