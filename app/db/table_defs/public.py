"""Re-exports of all public-schema tables from their owning domain modules.

Domain modules own their tables and define them in
``app/domain/{module}/tables.py``.  This file exists for backward
compatibility so that ``from app.db.table_defs import ...`` continues
to work.  New code should import directly from the owning module.
"""

from app.db.metadata import public_metadata
from app.domain.groups.tables import groups
from app.domain.courses.tables import course_completions, courses, group_course_requirements
from app.domain.volunteers.tables import volunteer_cards, volunteer_next_of_kin, volunteer_photos, volunteer_records
from app.domain.role_assignments.tables import assignment_roles, role_assignments
from app.domain.volunteer_applications.tables import (
    volunteer_application_group_members,
    volunteer_application_groups,
    volunteer_application_invites,
    volunteer_application_submissions,
)
from app.domain.mobile_card.tables import mobile_card_access_codes, mobile_card_april_state
from app.domain.spotify.tables import integration_tokens
from app.domain.admin_accounts.tables import group_admin_memberships, user_accounts, web_sessions

__all__ = [
    "assignment_roles",
    "course_completions",
    "courses",
    "group_admin_memberships",
    "group_course_requirements",
    "groups",
    "integration_tokens",
    "mobile_card_access_codes",
    "mobile_card_april_state",
    "public_metadata",
    "role_assignments",
    "user_accounts",
    "volunteer_application_group_members",
    "volunteer_application_groups",
    "volunteer_application_invites",
    "volunteer_application_submissions",
    "volunteer_cards",
    "volunteer_next_of_kin",
    "volunteer_photos",
    "volunteer_records",
    "web_sessions",
]
