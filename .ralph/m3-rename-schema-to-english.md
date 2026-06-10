# M3: Rename the database to English and fix column types

## Goals
1. Write migration `20260610_1100_rename_schema_to_english.py` — pure renames only
2. Write migration `20260610_1200_fix_column_types_and_fks.py` — type fixes and foreign keys  
3. Rewrite `app/db/table_defs/public.py` with English names matching the new DB names
4. Delete the alias block from `app/db/table_defs/__init__.py`
5. Sweep all Python code replacing Norwegian column references with English ones
6. `make test` and `make openapi-check` pass

## Concrete rename map (table then column)
Tables: personal→volunteer_records, personal_bilde→volunteer_photos, personal_kort→volunteer_cards, paarorende→volunteer_next_of_kin, grupper→groups, verv→assignment_roles, historie→role_assignments, kurs→courses, historie_kurs→course_completions, grupper_kurs_kobling→group_course_requirements, registrering→volunteer_application_invites, nytt_personal→volunteer_application_submissions, registrering_gruppe→volunteer_application_groups, registrering_gruppe_medlem→volunteer_application_group_members

Columns: fornavn→first_name, etternavn→last_name, epost→email, telefon→phone, fodselsdato→birth_date, kjonn→gender, gateadresse→street_address, postnummerid→postal_code, opprettet→created_at, navn→name, beskrivelse→description, aktiv→is_active, aktiv_til_og_med→active_through_semester, id_overgruppe→parent_group_id, rabatt_trinn→discount_tier, id_personal→volunteer_id, id_gruppe→group_id, id_verv→role_id, id_kurs→course_id, verv→name, pingvinpoeng→penguin_points, signert_kontrakt→contract_signed, gjennomfort_dato→completed_semester, kortnummer→card_number, gruppe_id→group_id, registrering_id→invite_id, registrering_epost→applicant_email, rolle→role, droppet→dropped_at, droppet_av_user_id→dropped_by_user_account_id, internkortaccesstoken→internkortaccesstoken (keep for now, moves in M6), internkort_access_token_created_at→internkort_access_token_created_at (keep for now)

## Steps
- [ ] M3a: Author the pure-rename migration file
- [ ] M3b: Author the type/FK fix migration file  
- [ ] M3c: Rewrite table_defs/public.py with English names
- [ ] M3d: Delete alias block from table_defs/__init__.py
- [ ] M3e: Find and replace all Norwegian column references in app/, tests/, scripts/
- [ ] M3f: Update the baseline migration's table/column names
- [ ] M3g: Run make test, make openapi-check, make lint
- [ ] M3h: Verify with grep that no Norwegian names remain (except in migrations)
