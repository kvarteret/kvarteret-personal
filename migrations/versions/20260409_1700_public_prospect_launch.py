"""public prospect launch support

Revision ID: 20260409_1700
Revises: 20260329_1300
Create Date: 2026-04-09 17:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260409_1700"
down_revision = "20260329_1300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "registrering",
        sa.Column("source", sa.Text(), server_default="invite", nullable=False),
    )
    op.add_column(
        "registrering",
        sa.Column("status", sa.Text(), server_default="invited", nullable=False),
    )
    op.add_column("registrering", sa.Column("first_choice_group_id", sa.BigInteger(), nullable=True))
    op.add_column("registrering", sa.Column("second_choice_group_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "registrering",
        sa.Column("trial_shift_attended", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("registrering", sa.Column("trial_shift_marked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("registrering", sa.Column("full_profile_submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("registrering", sa.Column("promoted_volunteer_id", sa.BigInteger(), nullable=True))
    op.add_column("registrering", sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_registrering_promoted_volunteer_id_personal",
        "registrering",
        "personal",
        ["promoted_volunteer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_registrering_first_choice_group_id",
        "registrering",
        ["first_choice_group_id"],
        unique=False,
    )
    op.create_index(
        "ix_registrering_second_choice_group_id",
        "registrering",
        ["second_choice_group_id"],
        unique=False,
    )
    op.create_index(
        "ix_registrering_promoted_volunteer_id",
        "registrering",
        ["promoted_volunteer_id"],
        unique=False,
    )

    op.add_column("nytt_personal", sa.Column("studiested", sa.Text(), nullable=True))
    op.add_column("nytt_personal", sa.Column("bakgrunn", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("nytt_personal", "bakgrunn")
    op.drop_column("nytt_personal", "studiested")

    op.drop_index("ix_registrering_promoted_volunteer_id", table_name="registrering")
    op.drop_index("ix_registrering_second_choice_group_id", table_name="registrering")
    op.drop_index("ix_registrering_first_choice_group_id", table_name="registrering")
    op.drop_constraint(
        "fk_registrering_promoted_volunteer_id_personal",
        "registrering",
        type_="foreignkey",
    )
    op.drop_column("registrering", "promoted_at")
    op.drop_column("registrering", "promoted_volunteer_id")
    op.drop_column("registrering", "full_profile_submitted_at")
    op.drop_column("registrering", "trial_shift_marked_at")
    op.drop_column("registrering", "trial_shift_attended")
    op.drop_column("registrering", "second_choice_group_id")
    op.drop_column("registrering", "first_choice_group_id")
    op.drop_column("registrering", "status")
    op.drop_column("registrering", "source")
