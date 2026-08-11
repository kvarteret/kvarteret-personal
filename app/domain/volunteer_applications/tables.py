"""Tables owned by the volunteer_applications module."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
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
    Column("id", BigInteger, primary_key=True),
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
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("token", name="uq_volunteer_application_invites_token"),
)

volunteer_application_groups = Table(
    "volunteer_application_groups",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

volunteer_application_group_members = Table(
    "volunteer_application_group_members",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("group_id", BigInteger, ForeignKey("public.volunteer_application_groups.id"), nullable=False),
    Column("invite_id", BigInteger, ForeignKey("public.volunteer_application_invites.id", ondelete=_SET_NULL)),
    Column("applicant_email", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("dropped_at", DateTime(timezone=True)),
    Column("dropped_by_user_account_id", BigInteger),
    CheckConstraint("role in ('inviter', 'invitee')", name="ck_volunteer_application_group_members_role"),
    CheckConstraint("status in ('active', 'dropped')", name="ck_volunteer_application_group_members_status"),
    UniqueConstraint("group_id", "invite_id", name="uq_volunteer_application_group_members_invite"),
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
)
