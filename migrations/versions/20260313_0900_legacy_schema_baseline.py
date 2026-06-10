"""baseline legacy personnel schema

Revision ID: 20260313_0900
Revises:
Create Date: 2026-03-13 09:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260313_0900"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("fornavn", sa.String(length=255), nullable=True),
        sa.Column("etternavn", sa.String(length=255), nullable=False),
        sa.Column("brukerkonto", sa.String(length=64), nullable=True),
        sa.Column("epost", sa.String(length=1024), nullable=True),
        sa.Column("arb_status", sa.Integer(), nullable=True),
        sa.Column("kjonn", sa.String(length=1), nullable=False),
        sa.Column("fodselsdato", sa.Date(), nullable=True),
        sa.Column("gateadresse", sa.String(length=128), nullable=True),
        sa.Column("postnummerid", sa.String(length=10), nullable=True),
        sa.Column("telefon", sa.String(length=50), nullable=True),
        sa.Column(
            "opprettet",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("internkortaccesstoken", sa.String(length=60), nullable=True),
        sa.Column("temp_column", sa.String(length=10), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.UniqueConstraint("email", name="personal_email_unique"),
    )
    op.create_index("idx_26652_etternavn", "personal", ["etternavn"])
    op.create_index("idx_26652_fornavn", "personal", ["fornavn"])

    op.create_table(
        "grupper",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("navn", sa.String(length=255), nullable=False),
        sa.Column("beskrivelse", sa.Text(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("aktiv_til_og_med", sa.Integer(), nullable=False),
        sa.Column(
            "opprettet",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.Column("id_overgruppe", sa.BigInteger(), nullable=True),
        sa.Column("rabatt_trinn", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id_overgruppe"],
            ["grupper.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="grupper_ibfk_1",
        ),
    )
    op.create_index("idx_26607_id_overgruppe", "grupper", ["id_overgruppe"])
    op.create_index("idx_26607_navn", "grupper", ["navn"], unique=True)

    op.create_table(
        "kurs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("navn", sa.String(length=128), nullable=False),
        sa.Column("beskrivelse", sa.String(length=1024), nullable=True),
        sa.Column(
            "opprettet",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )
    op.create_index("idx_26636_navn", "kurs", ["navn"], unique=True)

    op.create_table(
        "verv",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("verv", sa.String(length=255), nullable=True),
        sa.Column("id_gruppe", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("pingvinpoeng", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "opprettet",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["id_gruppe"],
            ["grupper.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="verv_ibfk_1",
        ),
    )
    op.create_index("idx_26677_id_gruppe", "verv", ["id_gruppe"])

    op.create_table(
        "personal_bilde",
        sa.Column("id_personal", sa.BigInteger(), primary_key=True),
        sa.Column("sha1", sa.String(length=40), nullable=False),
        sa.Column("filetype", sa.String(length=5), nullable=True),
        sa.Column(
            "opprettet",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["id_personal"],
            ["personal.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="personal_bilde_ibfk_1",
        ),
    )

    op.create_table(
        "paarorende",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("id_personal", sa.BigInteger(), nullable=False),
        sa.Column("navn", sa.String(length=512), nullable=False),
        sa.Column("telefon", sa.String(length=50), nullable=False),
        sa.Column(
            "opprettet",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["id_personal"],
            ["personal.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="paarorende_ibfk_1",
        ),
    )
    op.create_index("idx_26644_id_personal", "paarorende", ["id_personal"])

    op.create_table(
        "personal_kort",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("id_personal", sa.BigInteger(), nullable=False),
        sa.Column("kortnummer", sa.String(length=15), nullable=False),
        sa.Column(
            "opprettet",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["id_personal"],
            ["personal.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="personal_kort_ibfk_1",
        ),
    )
    op.create_index("idx_26671_id_personal", "personal_kort", ["id_personal"])
    op.create_index("idx_26671_id_personal_2", "personal_kort", ["id_personal", "kortnummer"], unique=True)

    op.create_table(
        "historie",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("id_personal", sa.BigInteger(), nullable=False),
        sa.Column("id_gruppe", sa.BigInteger(), nullable=False),
        sa.Column("id_verv", sa.BigInteger(), server_default=sa.text("1"), nullable=True),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("signert_kontrakt", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "opprettet",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["id_personal"], ["personal.id"], onupdate="CASCADE", name="historie_ibfk_1"),
        sa.ForeignKeyConstraint(["id_gruppe"], ["grupper.id"], onupdate="CASCADE", name="historie_ibfk_2"),
        sa.ForeignKeyConstraint(["id_verv"], ["verv.id"], onupdate="CASCADE", name="historie_ibfk_3"),
    )
    op.create_index("idx_26622_id_gruppe", "historie", ["id_gruppe"])
    op.create_index("idx_26622_id_personal", "historie", ["id_personal"])
    op.create_index("idx_26622_id_verv", "historie", ["id_verv"])

    op.create_table(
        "historie_kurs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("id_personal", sa.BigInteger(), nullable=False),
        sa.Column("id_kurs", sa.BigInteger(), nullable=False),
        sa.Column("gjennomfort_dato", sa.Integer(), nullable=False),
        sa.Column(
            "opprettet",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["id_personal"], ["personal.id"], onupdate="CASCADE", name="historie_kurs_ibfk_1"),
        sa.ForeignKeyConstraint(["id_kurs"], ["kurs.id"], onupdate="CASCADE", name="historie_kurs_ibfk_2"),
    )
    op.create_index("idx_26630_id_kurs", "historie_kurs", ["id_kurs"])
    op.create_index("idx_26630_id_personal", "historie_kurs", ["id_personal"])

    op.create_table(
        "grupper_kurs_kobling",
        sa.Column("id_kurs", sa.BigInteger(), primary_key=True),
        sa.Column("id_gruppe", sa.BigInteger(), primary_key=True),
        sa.ForeignKeyConstraint(
            ["id_kurs"],
            ["kurs.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="grupper_kurs_kobling_ibfk_1",
        ),
        sa.ForeignKeyConstraint(
            ["id_gruppe"],
            ["grupper.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="grupper_kurs_kobling_ibfk_2",
        ),
    )
    op.create_index("idx_26618_id_gruppe", "grupper_kurs_kobling", ["id_gruppe"])

    _create_retired_legacy_tables()


def downgrade() -> None:
    for table_name in (
        "volunteer_signup",
        "board_game_open_invite",
        "grupper_admin_kobling",
        "aspnetuserroles",
        "aspnetroles",
        "aspnetusers",
        "personal_fil",
        "grupper_kurs_kobling",
        "historie_kurs",
        "historie",
        "personal_kort",
        "paarorende",
        "personal_bilde",
        "verv",
        "kurs",
        "grupper",
        "personal",
    ):
        op.drop_table(table_name)


def _create_retired_legacy_tables() -> None:
    op.create_table(
        "aspnetusers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("accessfailedcount", sa.BigInteger(), nullable=False),
        sa.Column("concurrencystamp", sa.Text(), nullable=True),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email", sa.String(length=256), nullable=True),
        sa.Column("emailconfirmed", sa.Boolean(), nullable=False),
        sa.Column("lastlogin", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lockoutenabled", sa.Boolean(), nullable=False),
        sa.Column("lockoutend", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("normalizedemail", sa.String(length=256), nullable=True),
        sa.Column("normalizedusername", sa.String(length=256), nullable=True),
        sa.Column("passwordhash", sa.Text(), nullable=True),
        sa.Column("phonenumber", sa.Text(), nullable=True),
        sa.Column("phonenumberconfirmed", sa.Boolean(), nullable=False),
        sa.Column("securitystamp", sa.Text(), nullable=True),
        sa.Column("twofactorenabled", sa.Boolean(), nullable=False),
        sa.Column("username", sa.String(length=256), nullable=True),
    )

    op.create_table(
        "aspnetroles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("concurrencystamp", sa.Text(), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("normalizedname", sa.String(length=256), nullable=True),
    )

    op.create_table(
        "aspnetuserroles",
        sa.Column("userid", sa.BigInteger(), primary_key=True),
        sa.Column("roleid", sa.BigInteger(), primary_key=True),
        sa.ForeignKeyConstraint(["userid"], ["aspnetusers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["roleid"], ["aspnetroles.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_26591_fk_aspnetuserroles_aspnetroles_roleid", "aspnetuserroles", ["roleid"])

    op.create_table(
        "grupper_admin_kobling",
        sa.Column("id_user", sa.BigInteger(), primary_key=True),
        sa.Column("id_gruppe", sa.BigInteger(), primary_key=True),
        sa.ForeignKeyConstraint(
            ["id_user"],
            ["aspnetusers.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="user_kobling",
        ),
        sa.ForeignKeyConstraint(
            ["id_gruppe"],
            ["grupper.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="grupper_kobling",
        ),
    )
    op.create_index("idx_26615_grupper_kobling", "grupper_admin_kobling", ["id_gruppe"])

    op.create_table(
        "personal_fil",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("id_personal", sa.BigInteger(), nullable=False),
        sa.Column("gruppekobling", sa.BigInteger(), nullable=True),
        sa.Column("filename", sa.String(length=255), server_default='"INGEN NAVN"', nullable=False),
        sa.Column("filetype", sa.String(length=10), nullable=True),
        sa.Column(
            "opprettet",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["id_personal"],
            ["personal.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="fil-personal-fkid",
        ),
        sa.ForeignKeyConstraint(
            ["gruppekobling"],
            ["grupper.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="fil-gruppe-fkid",
        ),
    )
    op.create_index("idx_26664_id_gruppe", "personal_fil", ["gruppekobling"])
    op.create_index("idx_26664_id_personal", "personal_fil", ["id_personal"])

    op.create_table(
        "board_game_open_invite",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("game", sa.Text(), server_default="chess", nullable=False),
        sa.Column("room", sa.Text(), nullable=False),
        comment="open invitation for board game",
    )

    op.create_table(
        "volunteer_signup",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("group", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("institution", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        comment="blifrivillig.no form entries",
    )
