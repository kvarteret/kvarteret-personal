"""Track identity ownership and independent application batch responses.

Revision ID: 20261001_1300
Revises: 20261001_1200
"""

from alembic import op
import sqlalchemy as sa

revision = "20261001_1300"
down_revision = "20261001_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "volunteer_application_invites",
        sa.Column(
            "owns_volunteer_profile",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema="public",
    )
    # Before this change each linked identity was created by its sole application.
    op.execute("""UPDATE public.volunteer_application_invites
        SET owns_volunteer_profile = true WHERE id IN (
            SELECT min(id) FROM public.volunteer_application_invites
            WHERE promoted_volunteer_id IS NOT NULL GROUP BY promoted_volunteer_id
        )""")
    # Different request bodies may now continue the same existing application.
    op.drop_constraint(
        "volunteer_prospect_submissions_registration_id_key",
        "volunteer_prospect_submissions",
        schema="public",
        type_="unique",
    )
    op.add_column(
        "volunteer_prospect_submissions",
        sa.Column("registration_ids", sa.JSON(), nullable=True),
        schema="public",
    )


def downgrade() -> None:
    # This intentionally fails without deleting data if multiple request hashes
    # already reference an application. Roll back code before enabling the feature.
    op.create_unique_constraint(
        "volunteer_prospect_submissions_registration_id_key",
        "volunteer_prospect_submissions",
        ["registration_id"],
        schema="public",
    )
    op.drop_column(
        "volunteer_prospect_submissions", "registration_ids", schema="public"
    )
    op.drop_column(
        "volunteer_application_invites", "owns_volunteer_profile", schema="public"
    )
