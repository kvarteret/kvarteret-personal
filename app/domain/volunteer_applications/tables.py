"""Tables owned by the volunteer_applications module."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Table,
    Text,
    UniqueConstraint,
)

from app.db.metadata import public_metadata

_SET_NULL = "SET NULL"

volunteer_application_invites = Table(
    "volunteer_application_invites",
    public_metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("token", Text, nullable=False),
    Column("email", Text, nullable=False),
    Column("source", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("initial_group_id", BigInteger),
    Column("initial_role_id", BigInteger),
    Column("first_choice_group_id", BigInteger),
    Column("second_choice_group_id", BigInteger),
    Column("first_choice_label", Text),
    Column("second_choice_label", Text),
    Column("trial_shift_attended", Boolean, nullable=False),
    Column("trial_shift_marked_at", DateTime(timezone=True)),
    Column("trial_started_at", DateTime(timezone=True)),
    Column("trial_ends_at", DateTime(timezone=True)),
    Column("full_profile_submitted_at", DateTime(timezone=True)),
    Column("promoted_volunteer_id", BigInteger, ForeignKey("public.volunteer_records.id")),
    Column("promoted_at", DateTime(timezone=True)),
    Column("origin_trace_id", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("token", name="uq_volunteer_application_invites_token"),
)

volunteer_application_friend_invitations = Table(
    "volunteer_application_friend_invitations",
    public_metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column(
        "inviter_application_id",
        BigInteger,
        ForeignKey("public.volunteer_application_invites.id", ondelete=_SET_NULL),
    ),
    Column(
        "invitee_application_id",
        BigInteger,
        ForeignKey("public.volunteer_application_invites.id", ondelete=_SET_NULL),
    ),
    Column("inviter_name_snapshot", Text),
    Column("inviter_email_snapshot", Text, nullable=False),
    Column("invitee_email_snapshot", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("legacy_dropped_at", DateTime(timezone=True)),
    Column(
        "legacy_dropped_by_user_account_id",
        BigInteger,
        ForeignKey("public.user_accounts.id", ondelete=_SET_NULL),
    ),
    UniqueConstraint(
        "invitee_application_id",
        name="uq_volunteer_application_friend_invitations_invitee",
    ),
    Index(
        "ix_va_friend_invites_inviter_id",
        "inviter_application_id",
    ),
    Index(
        "ix_va_friend_invites_invitee_id",
        "invitee_application_id",
    ),
)

volunteer_application_submissions = Table(
    "volunteer_application_submissions",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("invite_id", BigInteger, ForeignKey("public.volunteer_application_invites.id"), nullable=False, unique=True),
    Column("first_name", Text),
    Column("last_name", Text, nullable=False),
    Column("email", Text, nullable=False),
    Column("gender", Text, nullable=False),
    Column("birth_date", DateTime(timezone=True)),
    Column("street_address", Text),
    Column("postal_code", Text),
    Column("phone", Text),
    Column("internkortaccesstoken", Text),
    Column("photo_sha1", Text),
    Column("photo_filetype", Text),
    Column("studiested", Text),
    Column("bakgrunn", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


domain_events = Table(
    "domain_events",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("event_type", Text, nullable=False),
    Column("actor_user_account_id", BigInteger, nullable=True),
    Column("subject_type", Text, nullable=False),
    Column("subject_id", BigInteger, nullable=False),
    Column("payload", JSON, nullable=False, server_default="{}"),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("trace_id", Text),
)
