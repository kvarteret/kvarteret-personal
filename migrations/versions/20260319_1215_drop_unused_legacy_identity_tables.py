"""drop empty unused legacy identity tables

Revision ID: 20260319_1215
Revises: 20260318_2015
Create Date: 2026-03-19 12:15:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260319_1215"
down_revision = "20260318_2015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.aspnetroleclaims")
    op.execute("DROP TABLE IF EXISTS public.aspnetuserclaims")
    op.execute("DROP TABLE IF EXISTS public.aspnetuserlogins")
    op.execute("DROP TABLE IF EXISTS public.aspnetusertokens")
    op.execute('DROP TABLE IF EXISTS public."__efmigrationshistory"')


def downgrade() -> None:
    op.create_table(
        "__efmigrationshistory",
        sa.Column("migrationid", sa.String(length=95), nullable=False),
        sa.Column("productversion", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("migrationid"),
        schema="public",
    )
    op.create_table(
        "aspnetroleclaims",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("claimtype", sa.Text(), nullable=True),
        sa.Column("claimvalue", sa.Text(), nullable=True),
        sa.Column("roleid", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["roleid"], ["public.aspnetroles.id"], name="fk_aspnetroleclaims_aspnetroles_roleid"),
        sa.PrimaryKeyConstraint("id"),
        schema="public",
    )
    op.create_table(
        "aspnetuserclaims",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("claimtype", sa.Text(), nullable=True),
        sa.Column("claimvalue", sa.Text(), nullable=True),
        sa.Column("userid", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["userid"], ["public.aspnetusers.id"], name="fk_aspnetuserclaims_aspnetusers_userid"),
        sa.PrimaryKeyConstraint("id"),
        schema="public",
    )
    op.create_table(
        "aspnetuserlogins",
        sa.Column("loginprovider", sa.String(length=127), nullable=False),
        sa.Column("providerkey", sa.String(length=127), nullable=False),
        sa.Column("providerdisplayname", sa.Text(), nullable=True),
        sa.Column("userid", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["userid"], ["public.aspnetusers.id"], name="fk_aspnetuserlogins_aspnetusers_userid"),
        sa.PrimaryKeyConstraint("loginprovider", "providerkey"),
        schema="public",
    )
    op.create_table(
        "aspnetusertokens",
        sa.Column("userid", sa.BigInteger(), nullable=False),
        sa.Column("loginprovider", sa.String(length=127), nullable=False),
        sa.Column("name", sa.String(length=127), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("userid", "loginprovider", "name"),
        schema="public",
    )
