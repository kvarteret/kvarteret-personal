"""preserve public application choice labels

Revision ID: 20260810_1400
Revises: 20260729_1300
Create Date: 2026-08-10 14:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260810_1400"
down_revision = "20260729_1300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "volunteer_application_invites",
        sa.Column("first_choice_label", sa.Text(), nullable=True),
    )
    op.add_column(
        "volunteer_application_invites",
        sa.Column("second_choice_label", sa.Text(), nullable=True),
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE volunteer_application_invites AS application
            SET first_choice_label = COALESCE(
                (
                    SELECT role.name
                    FROM assignment_roles AS role
                    WHERE role.id = application.initial_role_id
                ),
                (
                    SELECT selected_group.name
                    FROM groups AS selected_group
                    WHERE selected_group.id = application.first_choice_group_id
                )
            )
            WHERE application.first_choice_group_id IS NOT NULL
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE volunteer_application_invites AS application
            SET second_choice_label = (
                SELECT selected_group.name
                FROM groups AS selected_group
                WHERE selected_group.id = application.second_choice_group_id
            )
            WHERE application.second_choice_group_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("volunteer_application_invites", "second_choice_label")
    op.drop_column("volunteer_application_invites", "first_choice_label")
