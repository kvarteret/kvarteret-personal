from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, MetaData, String, Table, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID

public_metadata = MetaData(schema="public")
auth_metadata = MetaData(schema="auth")
storage_metadata = MetaData(schema="storage")

personal = Table(
    "personal",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("fornavn", Text),
    Column("etternavn", Text, nullable=False),
    Column("epost", Text),
    Column("telefon", Text),
    Column("fodselsdato", Date),
    Column("opprettet", DateTime(timezone=True), nullable=False),
    Column("kjonn", Text, nullable=False),
    Column("gateadresse", Text),
    Column("postnummerid", Text),
    Column("arb_status", Integer),
    Column("internkortaccesstoken", Text),
    Column("internkort_access_token_created_at", DateTime(timezone=True)),
)

personal_bilde = Table(
    "personal_bilde",
    public_metadata,
    Column("id_personal", BigInteger, ForeignKey("public.personal.id"), primary_key=True),
    Column("sha1", Text, nullable=False),
    Column("filetype", Text, nullable=False),
)

paarorende = Table(
    "paarorende",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("id_personal", BigInteger, ForeignKey("public.personal.id"), nullable=False),
    Column("navn", Text, nullable=False),
    Column("telefon", Text, nullable=False),
    Column("opprettet", DateTime(timezone=True), nullable=False),
)

personal_kort = Table(
    "personal_kort",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("id_personal", BigInteger, ForeignKey("public.personal.id"), nullable=False),
    Column("kortnummer", Text, nullable=False),
    Column("opprettet", DateTime(timezone=True), nullable=False),
)

personal_fil = Table(
    "personal_fil",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("id_personal", BigInteger, ForeignKey("public.personal.id"), nullable=False),
    Column("gruppekobling", BigInteger),
    Column("filename", Text, nullable=False),
    Column("filetype", Text),
    Column("opprettet", DateTime(timezone=True), nullable=False),
)

registrering = Table(
    "registrering",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("token", Text, nullable=False),
    Column("epost", Text, nullable=False),
    Column("opprettet", DateTime(timezone=True), nullable=False),
    UniqueConstraint("token", name="uq_registrering_token"),
)

nytt_personal = Table(
    "nytt_personal",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("registrering_id", BigInteger, ForeignKey("public.registrering.id"), nullable=False, unique=True),
    Column("fornavn", Text),
    Column("etternavn", Text, nullable=False),
    Column("epost", Text, nullable=False),
    Column("arb_status", Integer),
    Column("kjonn", Text, nullable=False),
    Column("fodselsdato", Date),
    Column("gateadresse", Text),
    Column("postnummerid", Text),
    Column("telefon", Text),
    Column("internkortaccesstoken", Text),
    Column("opprettet", DateTime(timezone=True), nullable=False),
)

grupper = Table(
    "grupper",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("navn", Text, nullable=False),
    Column("beskrivelse", Text),
    Column("aktiv", Boolean, nullable=False),
    Column("aktiv_til_og_med", Integer, nullable=False),
    Column("id_overgruppe", BigInteger),
    Column("rabatt_trinn", Integer),
    Column("opprettet", DateTime(timezone=True)),
)

verv = Table(
    "verv",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("verv", Text),
    Column("id_gruppe", BigInteger, ForeignKey("public.grupper.id"), nullable=False),
    Column("pingvinpoeng", Integer, nullable=False),
)

historie = Table(
    "historie",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("id_personal", BigInteger, ForeignKey("public.personal.id"), nullable=False),
    Column("id_gruppe", BigInteger, ForeignKey("public.grupper.id"), nullable=False),
    Column("id_verv", BigInteger, ForeignKey("public.verv.id")),
    Column("semester", Integer, nullable=False),
    Column("signert_kontrakt", Boolean, nullable=False),
)

kurs = Table(
    "kurs",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("navn", Text, nullable=False),
    Column("beskrivelse", Text),
    Column("opprettet", DateTime(timezone=True)),
)

historie_kurs = Table(
    "historie_kurs",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("id_personal", BigInteger, ForeignKey("public.personal.id"), nullable=False),
    Column("id_kurs", BigInteger, ForeignKey("public.kurs.id"), nullable=False),
    Column("gjennomfort_dato", Integer, nullable=False),
)

grupper_kurs_kobling = Table(
    "grupper_kurs_kobling",
    public_metadata,
    Column("id_kurs", BigInteger, ForeignKey("public.kurs.id"), primary_key=True),
    Column("id_gruppe", BigInteger, ForeignKey("public.grupper.id"), primary_key=True),
)

aspnetusers = Table(
    "aspnetusers",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("username", String(256)),
    Column("email", String(256)),
    Column("name", String(256)),
    Column("passwordhash", Text),
)

aspnetroles = Table(
    "aspnetroles",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", String(256), nullable=False),
)

aspnetuserroles = Table(
    "aspnetuserroles",
    public_metadata,
    Column("userid", BigInteger, primary_key=True),
    Column("roleid", BigInteger, primary_key=True),
)

grupper_admin_kobling = Table(
    "grupper_admin_kobling",
    public_metadata,
    Column("id_user", BigInteger, primary_key=True),
    Column("id_gruppe", BigInteger, primary_key=True),
)

user_accounts = Table(
    "user_accounts",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("auth_user_id", UUID(as_uuid=True), nullable=False),
    Column("legacy_user_id", BigInteger),
    Column("username", String(256), nullable=False),
    Column("email", String(320), nullable=False),
    Column("display_name", String(256)),
    Column("role", String(64), nullable=False),
    Column("last_login", DateTime(timezone=True)),
    Column("migrated_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

group_admin_memberships = Table(
    "group_admin_memberships",
    public_metadata,
    Column("auth_user_id", UUID(as_uuid=True), primary_key=True),
    Column("gruppe_id", BigInteger, ForeignKey("public.grupper.id"), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

web_sessions = Table(
    "web_sessions",
    public_metadata,
    Column("session_id", String(128), primary_key=True),
    Column("auth_user_id", UUID(as_uuid=True), nullable=False),
    Column("user_account_id", BigInteger, ForeignKey("public.user_accounts.id")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("ip_address", String(64)),
    Column("user_agent", Text),
)

auth_migration_events = Table(
    "auth_migration_events",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("legacy_user_id", BigInteger, nullable=False),
    Column("auth_user_id", UUID(as_uuid=True)),
    Column("email", String(320)),
    Column("outcome", String(64), nullable=False),
    Column("details", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

auth_users = Table(
    "users",
    auth_metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("email", String(320)),
)

auth_refresh_tokens = Table(
    "refresh_tokens",
    auth_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("user_id", String(255), nullable=False),
)

auth_sessions = Table(
    "sessions",
    auth_metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("user_id", UUID(as_uuid=True), nullable=False),
)

auth_identities = Table(
    "identities",
    auth_metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("user_id", UUID(as_uuid=True), nullable=False),
)

storage_objects = Table(
    "objects",
    storage_metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("bucket_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("owner", UUID(as_uuid=True)),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
    Column("last_accessed_at", DateTime(timezone=True)),
    Column("metadata", Text),
    Column("path_tokens", ARRAY(Text)),
    Column("version", Text),
)
