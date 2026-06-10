"""rename the database schema to English (pure renames, exactly reversible)

Revision ID: 20260610_1100
Revises: 20260610_1000
Create Date: 2026-06-10 11:00:00
"""
from alembic import op

revision = "20260610_1100"
down_revision = "20260610_1000"
branch_labels = None
depends_on = None

# Each entry: (table, old_name, new_name)
_TABLE_RENAMES = [
    ("personal", "volunteer_records"),
    ("personal_bilde", "volunteer_photos"),
    ("personal_kort", "volunteer_cards"),
    ("paarorende", "volunteer_next_of_kin"),
    ("grupper", "groups"),
    ("verv", "assignment_roles"),
    ("historie", "role_assignments"),
    ("kurs", "courses"),
    ("historie_kurs", "course_completions"),
    ("grupper_kurs_kobling", "group_course_requirements"),
    ("registrering", "volunteer_application_invites"),
    ("nytt_personal", "volunteer_application_submissions"),
    ("registrering_gruppe", "volunteer_application_groups"),
    ("registrering_gruppe_medlem", "volunteer_application_group_members"),
]

# Each entry: (table, old_name, new_name)
# The table name here is the NEW English name (because columns are renamed after tables)
_COLUMN_RENAMES = {
    "volunteer_records": [
        ("fornavn", "first_name"),
        ("etternavn", "last_name"),
        ("epost", "email"),
        ("telefon", "phone"),
        ("fodselsdato", "birth_date"),
        ("kjonn", "gender"),
        ("gateadresse", "street_address"),
        ("postnummerid", "postal_code"),
        ("opprettet", "created_at"),
    ],
    "volunteer_photos": [
        ("id_personal", "volunteer_id"),
        ("opprettet", "created_at"),
    ],
    "volunteer_next_of_kin": [
        ("id_personal", "volunteer_id"),
        ("navn", "name"),
        ("telefon", "phone"),
        ("opprettet", "created_at"),
    ],
    "volunteer_cards": [
        ("id_personal", "volunteer_id"),
        ("kortnummer", "card_number"),
        ("opprettet", "created_at"),
    ],
    "groups": [
        ("navn", "name"),
        ("beskrivelse", "description"),
        ("aktiv", "is_active"),
        ("aktiv_til_og_med", "active_through_semester"),
        ("id_overgruppe", "parent_group_id"),
        ("rabatt_trinn", "discount_tier"),
        ("opprettet", "created_at"),
    ],
    "assignment_roles": [
        ("verv", "name"),
        ("id_gruppe", "group_id"),
        ("pingvinpoeng", "penguin_points"),
        ("opprettet", "created_at"),
    ],
    "role_assignments": [
        ("id_personal", "volunteer_id"),
        ("id_gruppe", "group_id"),
        ("id_verv", "role_id"),
        ("signert_kontrakt", "contract_signed"),
        ("opprettet", "created_at"),
    ],
    "courses": [
        ("navn", "name"),
        ("beskrivelse", "description"),
        ("opprettet", "created_at"),
    ],
    "course_completions": [
        ("id_personal", "volunteer_id"),
        ("id_kurs", "course_id"),
        ("gjennomfort_dato", "completed_semester"),
        ("opprettet", "created_at"),
    ],
    "group_course_requirements": [
        ("id_kurs", "course_id"),
        ("id_gruppe", "group_id"),
    ],
    "volunteer_application_invites": [
        ("epost", "email"),
        ("opprettet", "created_at"),
    ],
    "volunteer_application_submissions": [
        ("registrering_id", "invite_id"),
        ("fornavn", "first_name"),
        ("etternavn", "last_name"),
        ("epost", "email"),
        ("kjonn", "gender"),
        ("fodselsdato", "birth_date"),
        ("gateadresse", "street_address"),
        ("postnummerid", "postal_code"),
        ("telefon", "phone"),
        ("opprettet", "created_at"),
    ],
    "volunteer_application_groups": [
        ("opprettet", "created_at"),
    ],
    "volunteer_application_group_members": [
        ("gruppe_id", "group_id"),
        ("registrering_id", "invite_id"),
        ("registrering_epost", "applicant_email"),
        ("rolle", "role"),
        ("opprettet", "created_at"),
        ("droppet", "dropped_at"),
        ("droppet_av_user_id", "dropped_by_user_account_id"),
    ],
}

# Constraints/indexes to rename (schema-qualified)
# Entries: (current_full_name, new_name)
_CONSTRAINT_RENAMES = [
    # On volunteer_application_invites (was registrering)
    ("volunteer_application_invites", "uq_registrering_token", "uq_volunteer_application_invites_token"),
    # On volunteer_application_group_members (was registrering_gruppe_medlem)
    ("volunteer_application_group_members", "ck_registrering_gruppe_medlem_rolle", "ck_volunteer_application_group_members_role"),
    ("volunteer_application_group_members", "ck_registrering_gruppe_medlem_status", "ck_volunteer_application_group_members_status"),
    ("volunteer_application_group_members", "uq_registrering_gruppe_medlem_registrering", "uq_volunteer_application_group_members_invite"),
]


def upgrade() -> None:
    # 1. Rename tables first
    for old_name, new_name in _TABLE_RENAMES:
        op.execute(f'ALTER TABLE "{old_name}" RENAME TO "{new_name}"')

    # 2. Rename columns
    for table, renames in _COLUMN_RENAMES.items():
        for old_col, new_col in renames:
            op.execute(f'ALTER TABLE "{table}" RENAME COLUMN "{old_col}" TO "{new_col}"')

    # 3. Rename constraints and indexes
    for table, old_name, new_name in _CONSTRAINT_RENAMES:
        op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"')


def downgrade() -> None:
    # Reverse: constraints first, then columns, then tables

    # 1. Rename constraints back
    for table, old_name, new_name in _CONSTRAINT_RENAMES:
        op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{new_name}" TO "{old_name}"')

    # 2. Rename columns back
    for table, renames in _COLUMN_RENAMES.items():
        for old_col, new_col in reversed(renames):
            op.execute(f'ALTER TABLE "{table}" RENAME COLUMN "{new_col}" TO "{old_col}"')

    # 3. Rename tables back
    for old_name, new_name in reversed(_TABLE_RENAMES):
        op.execute(f'ALTER TABLE "{new_name}" RENAME TO "{old_name}"')
