"""Track the exact role assignment created when a trial starts.

Revision ID: 20261001_1200
Revises: 20260824_1000
"""

from alembic import op
import sqlalchemy as sa

revision = "20261001_1200"
down_revision = "20260824_1000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "volunteer_application_invites",
        sa.Column("trial_assignment_id", sa.BigInteger(), nullable=True),
        schema="public",
    )
    op.create_foreign_key(
        "fk_volunteer_application_trial_assignment",
        "volunteer_application_invites",
        "role_assignments",
        ["trial_assignment_id"],
        ["id"],
        source_schema="public",
        referent_schema="public",
        ondelete="SET NULL",
    )
    # Backfill only unambiguous matches. Unknown legacy assignments are preserved;
    # approval creates a new assignment rather than guessing which one to overwrite.
    op.execute("""
        UPDATE public.volunteer_application_invites AS application
        SET trial_assignment_id = candidate.assignment_id
        FROM (
            SELECT application.id, min(assignment.id) AS assignment_id
            FROM public.volunteer_application_invites AS application
            JOIN public.role_assignments AS assignment
              ON assignment.volunteer_id = application.promoted_volunteer_id
             AND assignment.group_id = coalesce(application.initial_group_id, application.first_choice_group_id)
             AND assignment.role_id IS NOT DISTINCT FROM application.initial_role_id
             AND assignment.contract_signed IS FALSE
            WHERE application.trial_started_at IS NOT NULL AND application.promoted_at IS NULL
            GROUP BY application.id
            HAVING count(*) = 1
        ) AS candidate
        WHERE application.id = candidate.id
    """)


def downgrade() -> None:
    op.drop_constraint(
        "fk_volunteer_application_trial_assignment",
        "volunteer_application_invites",
        schema="public",
        type_="foreignkey",
    )
    op.drop_column(
        "volunteer_application_invites", "trial_assignment_id", schema="public"
    )
