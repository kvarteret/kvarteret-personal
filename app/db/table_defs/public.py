from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

_VOLUNTEER_RECORDS_ID_FK = "public.volunteer_records.id"
_GROUPS_ID_FK = "public.groups.id"
_USER_ACCOUNTS_ID_FK = "public.user_accounts.id"
_SET_NULL = "SET NULL"
_CASCADE = "CASCADE"

public_metadata = MetaData(schema="public")

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
    Column("internkortaccesstoken", Text),
    Column("internkort_access_token_created_at", DateTime(timezone=True)),
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
    Column("trial_shift_attended", Boolean, nullable=False),
    Column("trial_shift_marked_at", DateTime(timezone=True)),
    Column("full_profile_submitted_at", DateTime(timezone=True)),
    Column("promoted_volunteer_id", BigInteger, ForeignKey(_VOLUNTEER_RECORDS_ID_FK)),
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
    Column(
        "group_id",
        BigInteger,
        ForeignKey("public.volunteer_application_groups.id"),
        nullable=False,
    ),
    Column(
        "invite_id",
        BigInteger,
        ForeignKey("public.volunteer_application_invites.id", ondelete=_SET_NULL),
    ),
    Column("applicant_email", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("dropped_at", DateTime(timezone=True)),
    Column("dropped_by_user_account_id", BigInteger),
    CheckConstraint(
        "role in ('inviter', 'invitee')",
        name="ck_volunteer_application_group_members_role",
    ),
    CheckConstraint(
        "status in ('active', 'dropped')",
        name="ck_volunteer_application_group_members_status",
    ),
    UniqueConstraint(
        "group_id",
        "invite_id",
        name="uq_volunteer_application_group_members_invite",
    ),
)

volunteer_application_submissions = Table(
    "volunteer_application_submissions",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column(
        "invite_id",
        BigInteger,
        ForeignKey("public.volunteer_application_invites.id"),
        nullable=False,
        unique=True,
    ),
    Column("first_name", Text),
    Column("last_name", Text, nullable=False),
    Column("email", Text, nullable=False),
    Column("gender", Text, nullable=False),
    Column("birth_date", Date),
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

groups = Table(
    "groups",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", Text, nullable=False),
    Column("description", Text),
    Column("is_active", Boolean, nullable=False),
    Column("active_through_semester", Integer, nullable=False),
    Column("parent_group_id", BigInteger),
    Column("discount_tier", Integer),
    Column("created_at", DateTime(timezone=True)),
)

assignment_roles = Table(
    "assignment_roles",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", Text),
    Column("group_id", BigInteger, ForeignKey(_GROUPS_ID_FK), nullable=False),
    Column("penguin_points", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True)),
)

role_assignments = Table(
    "role_assignments",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("volunteer_id", BigInteger, ForeignKey(_VOLUNTEER_RECORDS_ID_FK), nullable=False),
    Column("group_id", BigInteger, ForeignKey(_GROUPS_ID_FK), nullable=False),
    Column("role_id", BigInteger, ForeignKey("public.assignment_roles.id")),
    Column("semester", Integer, nullable=False),
    Column("contract_signed", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True)),
)

courses = Table(
    "courses",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", Text, nullable=False),
    Column("description", Text),
    Column("created_at", DateTime(timezone=True)),
)

course_completions = Table(
    "course_completions",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("volunteer_id", BigInteger, ForeignKey(_VOLUNTEER_RECORDS_ID_FK), nullable=False),
    Column("course_id", BigInteger, ForeignKey("public.courses.id"), nullable=False),
    Column("completed_semester", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True)),
)

group_course_requirements = Table(
    "group_course_requirements",
    public_metadata,
    Column("course_id", BigInteger, ForeignKey("public.courses.id"), primary_key=True),
    Column("group_id", BigInteger, ForeignKey(_GROUPS_ID_FK), primary_key=True),
)

user_accounts = Table(
    "user_accounts",
    public_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("auth_user_id", UUID(as_uuid=True), nullable=False),
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
    Column("group_id", BigInteger, ForeignKey(_GROUPS_ID_FK), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

web_sessions = Table(
    "web_sessions",
    public_metadata,
    Column("session_id", String(128), primary_key=True),
    Column("auth_user_id", UUID(as_uuid=True), nullable=False),
    Column("user_account_id", BigInteger, ForeignKey(_USER_ACCOUNTS_ID_FK)),
    Column("impersonator_auth_user_id", UUID(as_uuid=True)),
    Column(
        "impersonator_user_account_id", BigInteger, ForeignKey(_USER_ACCOUNTS_ID_FK)
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("ip_address", String(64)),
    Column("user_agent", Text),
)

integration_tokens = Table(
    "integration_tokens",
    public_metadata,
    Column("provider", String(64), primary_key=True),
    Column("refresh_token", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("updated_by_user_account_id", BigInteger, ForeignKey(_USER_ACCOUNTS_ID_FK)),
)

mobile_card_april_state = Table(
    "mobile_card_april_state",
    public_metadata,
    Column("enabled", Boolean, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column(
        "updated_by_user_account_id",
        BigInteger,
        ForeignKey(_USER_ACCOUNTS_ID_FK, ondelete=_SET_NULL),
    ),
)