"""Tables owned by the mobile_card module."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Table, Text

from app.db.metadata import public_metadata

mobile_card_april_state = Table(
    "mobile_card_april_state",
    public_metadata,
    Column("enabled", Boolean, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column(
        "updated_by_user_account_id",
        BigInteger,
        ForeignKey("public.user_accounts.id", ondelete="SET NULL"),
    ),
)

mobile_card_access_codes = Table(
    "mobile_card_access_codes",
    public_metadata,
    Column("volunteer_id", BigInteger, ForeignKey("public.volunteer_records.id"), primary_key=True),
    Column("code_hash", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
