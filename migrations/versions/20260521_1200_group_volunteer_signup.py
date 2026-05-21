"""group volunteer signup audit tables

Revision ID: 20260521_1200
Revises: 20260506_2000
Create Date: 2026-05-21 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260521_1200"
down_revision = "20260506_2000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registrering_gruppe",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("opprettet", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "registrering_gruppe_medlem",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("gruppe_id", sa.BigInteger(), nullable=False),
        sa.Column("registrering_id", sa.BigInteger(), nullable=True),
        sa.Column("registrering_epost", sa.Text(), nullable=False),
        sa.Column("rolle", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("opprettet", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("droppet", sa.DateTime(timezone=True), nullable=True),
        sa.Column("droppet_av_user_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("rolle in ('inviter', 'invitee')", name="ck_registrering_gruppe_medlem_rolle"),
        sa.CheckConstraint("status in ('active', 'dropped')", name="ck_registrering_gruppe_medlem_status"),
        sa.ForeignKeyConstraint(["gruppe_id"], ["registrering_gruppe.id"]),
        sa.ForeignKeyConstraint(["registrering_id"], ["registrering.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("gruppe_id", "registrering_id", name="uq_registrering_gruppe_medlem_registrering"),
    )
    op.create_index(
        "ix_registrering_gruppe_medlem_gruppe_id",
        "registrering_gruppe_medlem",
        ["gruppe_id"],
        unique=False,
    )
    op.create_index(
        "ix_registrering_gruppe_medlem_registrering_id",
        "registrering_gruppe_medlem",
        ["registrering_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_registrering_gruppe_medlem_registrering_id", table_name="registrering_gruppe_medlem")
    op.drop_index("ix_registrering_gruppe_medlem_gruppe_id", table_name="registrering_gruppe_medlem")
    op.drop_table("registrering_gruppe_medlem")
    op.drop_table("registrering_gruppe")
