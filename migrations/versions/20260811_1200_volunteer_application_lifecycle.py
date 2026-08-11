"""add five-state volunteer application lifecycle and trial access

Revision ID: 20260811_1200
Revises: 20260810_1400
Create Date: 2026-08-11 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_1200"
down_revision = "20260810_1400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "volunteer_application_invites",
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "volunteer_application_invites",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "ALTER TABLE volunteer_application_invites "
        "DROP CONSTRAINT IF EXISTS ck_application_status"
    )
    op.execute(
        """
        UPDATE volunteer_application_invites
        SET status = CASE status
            WHEN 'promoted' THEN 'volunteer'
            WHEN 'rejected' THEN 'not_volunteer'
            ELSE 'new'
        END
        """
    )
    op.execute(
        """
        ALTER TABLE volunteer_application_invites
        ADD CONSTRAINT ck_application_status
        CHECK (status IN ('new', 'contacted', 'trial', 'volunteer', 'not_volunteer'))
        """
    )
    op.create_table(
        "mobile_card_trial_access_codes",
        sa.Column(
            "application_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "volunteer_application_invites.id", ondelete="CASCADE"
            ),
            primary_key=True,
        ),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("mobile_card_trial_access_codes")
    op.execute(
        "ALTER TABLE volunteer_application_invites "
        "DROP CONSTRAINT IF EXISTS ck_application_status"
    )
    op.execute(
        """
        UPDATE volunteer_application_invites
        SET status = CASE status
            WHEN 'volunteer' THEN 'promoted'
            WHEN 'not_volunteer' THEN 'rejected'
            WHEN 'trial' THEN 'submitted'
            WHEN 'contacted' THEN 'submitted'
            ELSE CASE
                WHEN full_profile_submitted_at IS NULL THEN 'invited'
                ELSE 'submitted'
            END
        """
    )
    op.execute(
        """
        ALTER TABLE volunteer_application_invites
        ADD CONSTRAINT ck_application_status
        CHECK (status IN ('prospect', 'invited', 'submitted', 'promoted', 'rejected'))
        """
    )
    op.drop_column("volunteer_application_invites", "trial_ends_at")
    op.drop_column("volunteer_application_invites", "trial_started_at")
