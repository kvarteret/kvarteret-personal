# 2026-06-10 Pre-Restructure Schema Inventory

Captured from production using:

    pg_dump "$DATABASE_URL" --schema-only --schema=public --no-owner --no-privileges

The schema snapshot is committed beside this inventory as
`20260610-pre-restructure.sql`.

## Alembic State

Production `public.alembic_version` was `20260521_1200` at capture time. The
local branch has a later unapplied revision, `20260610_1000`, for retired event
table removal.

## Production Row Counts for Drop Candidates

| Object | Rows | Disposition |
| --- | ---: | --- |
| `aspnetusers` | 66 | Export privately, then drop in M2 |
| `aspnetroles` | 3 | Export privately with ASP.NET identity archive, then drop in M2 |
| `aspnetuserroles` | 61 | Export privately with ASP.NET identity archive, then drop in M2 |
| `grupper_admin_kobling` | 40 | Export privately, then drop in M2; replaced by `group_admin_memberships` |
| `personal_fil` | 88 | Export privately, then drop in M2; document feature is retired |
| `events` | 47 | Export privately, then drop in M2; event table support is retired |
| `event_types` | 17 | Export privately with event archive, then drop in M2 |
| `event_organizer_groups` | 14 | Export privately with event archive, then drop in M2 |
| `event_organizer_group_memberships` | 40 | Export privately with event archive, then drop in M2 |
| `rooms` | 10 | Export privately with event archive, then drop in M2 |
| `board_game_open_invite` | 0 | Drop in M2; no app or sibling source references found |
| `volunteer_signup` | 1 | Export privately, then drop in M2; no app or sibling source references found |

## Metadata Drift

After adding the historically populated `opprettet` timestamp columns to
SQLAlchemy metadata and removing M2 drop-table metadata, `make schema-drift`
reports only objects with a drop/archive disposition:

    Extra database tables:
      + aspnetroles
      + aspnetuserroles
      + aspnetusers
      + board_game_open_invite
      + event_organizer_group_memberships
      + event_organizer_groups
      + event_types
      + events
      + grupper_admin_kobling
      + personal_fil
      + rooms
      + volunteer_signup
    Column drift in nytt_personal:
      + arb_status
    Column drift in personal:
      + arb_status
      + brukerkonto
      + email
      + temp_column

Column aggregate checks:

| Column | Aggregate result | Disposition |
| --- | --- | --- |
| `personal.arb_status` | 1 non-null of 10063 | Export in private column archive, then drop after M0 disposition |
| `personal.brukerkonto` | 0 non-null of 10063 | Drop after M0 disposition |
| `personal.email` | 6083 non-null; 6079 match `epost`, 4 differ | Export in private column archive, then drop after M0 disposition |
| `personal.temp_column` | 0 non-null of 10063 | Drop after M0 disposition |
| `nytt_personal.arb_status` | 0 non-null of 19 | Drop after M0 disposition |
| `historie.opprettet` | 20939 non-null of 27971 | Keep and rename to `created_at` in M3 |
| `historie_kurs.opprettet` | 3476 non-null of 3478 | Keep and rename to `created_at` in M3 |
| `personal_bilde.opprettet` | 5508 non-null of 5646 | Keep and rename to `created_at` in M3 |
| `verv.opprettet` | 253 non-null of 471 | Keep and rename to `created_at` in M3 |

## RLS and Auth Inventory

Public policies using `authenticated` or `auth.uid()`:

| Table | Policy | Roles | Expression |
| --- | --- | --- | --- |
| `grupper` | `grupper_select_self_authenticated` | `authenticated` | Checks membership through `historie` and `current_legacy_user_id()` |
| `historie` | `historie_select_self_authenticated` | `authenticated` | `id_personal = current_legacy_user_id()` |
| `personal` | `personal_select_self_authenticated` | `authenticated` | `id = current_legacy_user_id()` |
| `personal_bilde` | `personal_bilde_select_self_authenticated` | `authenticated` | `id_personal = current_legacy_user_id()` |
| `user_accounts` | `user_accounts_select_self_authenticated` | `authenticated` | `auth.uid() = auth_user_id` |
| `verv` | `verv_select_self_authenticated` | `authenticated` | Checks role assignments through `historie` and `current_legacy_user_id()` |

The function `public.current_legacy_user_id()` calls `auth.uid()` and maps the
Supabase Auth user to `user_accounts.legacy_user_id`. M9 must remove or replace
this function and the policies above when volunteers leave `auth.users`.

Public policy not tied to Supabase Auth:

| Table | Policy | Disposition |
| --- | --- | --- |
| `volunteer_signup` | `Enable insert for all` | Drop with the table in M2 after private export |

Storage policies:

| Table | Policy | Roles | Disposition |
| --- | --- | --- | --- |
| `storage.objects` | `Anyone can delete event images` | `anon`, `authenticated` | Drop in M2 with retired event surface |
| `storage.objects` | `Anyone can update event images` | `anon`, `authenticated` | Drop in M2 with retired event surface |
| `storage.objects` | `Anyone can upload event images` | `anon`, `authenticated` | Drop in M2 with retired event surface |
| `storage.objects` | `Public event images are readable` | `public` | Drop in M2 with retired event surface |

## Baseline Rehearsal Note

The captured schema can be replayed into a vanilla Postgres 17 container after
creating Supabase compatibility roles (`anon`, `authenticated`, `service_role`),
a stub `auth.uid()` function, and the `pg_trgm` extension.

Attempting to derive the pre-`20260313_1015` baseline by stamping the replayed
database to `20260521_1200` and running `alembic downgrade base` is blocked by
`20260325_1300_reconcile_event_schema_under_alembic.py`, whose downgrade raises
`RuntimeError("Downgrade is not supported for reconciled event schema ownership.")`.
The baseline must therefore be authored directly from the inventory instead of
being mechanically derived through the existing downgrade chain.
