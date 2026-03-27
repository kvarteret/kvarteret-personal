from app.db.table_defs.auth import auth_identities, auth_metadata, auth_refresh_tokens, auth_sessions, auth_users
from app.db.table_defs.public import (
    aspnetroles,
    aspnetuserroles,
    aspnetusers,
    auth_migration_events,
    event_organizer_group_memberships,
    event_organizer_groups,
    event_types,
    events,
    group_admin_memberships,
    grupper,
    grupper_admin_kobling,
    grupper_kurs_kobling,
    historie,
    historie_kurs,
    integration_tokens,
    kurs,
    nytt_personal,
    paarorende,
    personal,
    personal_bilde,
    personal_fil,
    personal_kort,
    public_metadata,
    registrering,
    rooms,
    user_accounts,
    verv,
    web_sessions,
)
from app.db.table_defs.storage import storage_metadata, storage_objects

admin_account_group_memberships = group_admin_memberships
assignment_roles = verv
course_completions = historie_kurs
courses = kurs
group_course_requirements = grupper_kurs_kobling
group_hierarchy = grupper_admin_kobling
groups = grupper
role_assignments = historie
volunteer_application_invites = registrering
volunteer_application_submissions = nytt_personal
volunteer_cards = personal_kort
volunteer_documents = personal_fil
volunteer_next_of_kin = paarorende
volunteer_photos = personal_bilde
volunteer_records = personal

__all__ = [
    "admin_account_group_memberships",
    "assignment_roles",
    "aspnetroles",
    "aspnetuserroles",
    "aspnetusers",
    "auth_identities",
    "auth_metadata",
    "auth_migration_events",
    "auth_refresh_tokens",
    "auth_sessions",
    "auth_users",
    "event_organizer_group_memberships",
    "event_organizer_groups",
    "event_types",
    "events",
    "course_completions",
    "courses",
    "group_admin_memberships",
    "group_course_requirements",
    "group_hierarchy",
    "groups",
    "grupper",
    "grupper_admin_kobling",
    "grupper_kurs_kobling",
    "historie",
    "historie_kurs",
    "integration_tokens",
    "kurs",
    "nytt_personal",
    "paarorende",
    "personal",
    "personal_bilde",
    "personal_fil",
    "personal_kort",
    "public_metadata",
    "registrering",
    "rooms",
    "storage_metadata",
    "storage_objects",
    "user_accounts",
    "verv",
    "role_assignments",
    "volunteer_application_invites",
    "volunteer_application_submissions",
    "volunteer_cards",
    "volunteer_documents",
    "volunteer_next_of_kin",
    "volunteer_photos",
    "volunteer_records",
    "web_sessions",
]
