"""registration and mobile card support

Revision ID: 20260313_1945
Revises: 20260313_1015
Create Date: 2026-03-13 19:45:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260313_1945"
down_revision = "20260313_1015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "personal",
        sa.Column("internkort_access_token_created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "registrering",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("epost", sa.Text(), nullable=False),
        sa.Column("opprettet", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("token", name="uq_registrering_token"),
    )

    op.create_table(
        "nytt_personal",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("registrering_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("fornavn", sa.Text(), nullable=True),
        sa.Column("etternavn", sa.Text(), nullable=False),
        sa.Column("epost", sa.Text(), nullable=False),
        sa.Column("arb_status", sa.Integer(), nullable=True),
        sa.Column("kjonn", sa.Text(), nullable=False, server_default="A"),
        sa.Column("fodselsdato", sa.Date(), nullable=True),
        sa.Column("gateadresse", sa.Text(), nullable=True),
        sa.Column("postnummerid", sa.Text(), nullable=True),
        sa.Column("telefon", sa.Text(), nullable=True),
        sa.Column("internkortaccesstoken", sa.Text(), nullable=True),
        sa.Column("opprettet", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["registrering_id"], ["registrering.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("nytt_personal")
    op.drop_table("registrering")
    op.drop_column("personal", "internkort_access_token_created_at")
