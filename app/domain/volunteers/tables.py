"""Tables owned by the volunteers module."""

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Table, Text

from app.db.metadata import public_metadata

_VOLUNTEER_RECORDS_ID_FK = "public.volunteer_records.id"

volunteer_records = Table(
    "volunteer_records",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("first_name", Text),
    Column("last_name", Text, nullable=False),
    Column("email", Text),
    Column("phone", Text),
    Column("birth_date", Date),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("gender", Text, nullable=False),
    Column("street_address", Text),
    Column("postal_code", Text),
)

volunteer_photos = Table(
    "volunteer_photos",
    public_metadata,
    Column("volunteer_id", BigInteger, ForeignKey(_VOLUNTEER_RECORDS_ID_FK), primary_key=True),
    Column("sha1", Text, nullable=False),
    Column("filetype", Text, nullable=False),
    Column("created_at", DateTime(timezone=True)),
)

volunteer_next_of_kin = Table(
    "volunteer_next_of_kin",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("volunteer_id", BigInteger, ForeignKey(_VOLUNTEER_RECORDS_ID_FK), nullable=False),
    Column("name", Text, nullable=False),
    Column("phone", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

volunteer_cards = Table(
    "volunteer_cards",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("volunteer_id", BigInteger, ForeignKey(_VOLUNTEER_RECORDS_ID_FK), nullable=False),
    Column("card_number", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
