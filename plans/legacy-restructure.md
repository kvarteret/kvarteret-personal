# Finish the .NET-era cleanup: baseline the schema, drop dead legacy structures, rename the database to English, retire the legacy mobile API, and align the codebase with ADR-001

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `/PLANS.md` at the repository root.

## Purpose / Big Picture

`kvarteret-personal` replaced a legacy ASP.NET 8 backend ("Personaldatabase_Backend") and its Angular frontend. The replacement is live at `personal.kvarteret.no`, but the migration was deliberately conservative: the Supabase Postgres database still carries the legacy Norwegian schema copied from the .NET app (`personal`, `grupper`, `historie`, `verv`, `kurs`, ...), the dead ASP.NET Identity tables (`aspnetusers`, `aspnetroles`, `aspnetuserroles`), a deprecated compatibility API (`/api/DigitalInternkort/*`), and a Python alias layer that papers over the naming gap (`volunteer_cards = personal_kort`). There is no Alembic baseline of the inherited schema and no CI pipeline that proves migrations or tests on every push.

Kvarteret is the only consumer of this system. All clients (`kvarteret-internbevis-rn`, `samfunnetibergen`, `frontend-eventside`) are owned by the same organization, so the database may be migrated and modified at will, provided the cutovers documented here are followed.

After this plan is complete:

- The database speaks the same English domain language as the code. `select * from volunteer_records` works; `personal` no longer exists. The alias layer in `app/db/table_defs/__init__.py` is gone.
- Every dead legacy structure is dropped from production: the three remaining `aspnet*` tables, `grupper_admin_kobling`, `personal_fil`, and (after the bridge audit) `auth_migration_events` and `user_accounts.legacy_user_id`.
- `/api/DigitalInternkort/*` is removed from the API surface, gated on measured zero traffic.
- Alembic has a true baseline of the production schema, and a CI workflow proves on every push that the test suite passes, `openapi.json` is current, and the migration chain applies cleanly from the baseline to head on a disposable Postgres.
- The two oversized domain modules (`volunteers`, `volunteer_applications`) are split along the read/write and workflow lines that ADR-001 (`docs/adr/001-modular-monolith-event-bus.md`) already established.

A reader can verify the end state by running `make test` (all green), `make openapi-check` (clean), inspecting the database with `\dt public.*` (English names only), and requesting `POST /api/DigitalInternkort/RequestAccessTokenOnEmail` (404).

## Progress

- [x] (2026-06-10) Research completed: schema inventory, dead-table audit, API surface audit, client boundary audit, CI audit. Findings recorded in `Surprises & Discoveries`.
- [ ] M0: Schema baseline and drift audit.
- [ ] M1: Drop dead legacy structures.
- [ ] M2: Rename the database to English and fix column types.
- [ ] M3: Retire the legacy DigitalInternkort API and auth-bridge vestiges (traffic-gated; can run in parallel with M2).
- [ ] M4: Code restructure — delete the alias layer, extract role assignments, split oversized services.
- [ ] M5: CI pipeline and schema-drift guardrails.

## Surprises & Discoveries

Findings from the research phase (2026-06-10). Update this section as implementation reveals more.

- Observation: The legacy ASP.NET Identity tables are dead code. `aspnetusers`, `aspnetroles`, and `aspnetuserroles` are defined in `app/db/table_defs/public.py` but no repository, service, or script queries them. Migration `20260319_1215_drop_unused_legacy_identity_tables.py` already dropped the empty claims/logins/tokens tables and `__efmigrationshistory`, but kept these three.
  Evidence: `grep -rn "aspnet" app --include='*.py'` matches only `table_defs` and `tables.py`.

- Observation: Login no longer touches legacy password hashes. `app/auth/login_service.py` authenticates directly against Supabase Auth (`sign_in_with_password`); the method is still named `login_with_bridge` but contains no bridge. `user_accounts.legacy_user_id` and `auth_migration_events` are write-only vestiges.
  Evidence: `login_with_bridge` body in `app/auth/login_service.py`; `auth_migration_events` has zero references outside table definitions.

- Observation: `grupper_admin_kobling` (the old .NET user→group admin coupling) is unused; the replacement is `group_admin_memberships`. The alias `group_hierarchy = grupper_admin_kobling` in `app/db/table_defs/__init__.py` is also a misnomer — the table never held a group hierarchy (that lives in `grupper.id_overgruppe`).
  Evidence: `grep -rn "group_hierarchy\|grupper_admin_kobling" app --include='*.py'` matches only the table-definition modules.

- Observation: `personal_fil` is dead. The documents feature was removed from the volunteers module (commit `13d26ad`, ADR-001 "Cleanup Decisions"), and `tests/web/volunteers/test_volunteers_web.py::test_volunteer_upload_endpoints_are_not_available` asserts the routes are gone. The table and its `volunteer_documents` alias remain defined.
  Evidence: zero non-definition references to `personal_fil`/`volunteer_documents` in `app/`.

- Observation: The Python alias layer translates names but not columns. `app/db/table_defs/__init__.py` assigns English aliases (`volunteer_records = personal`, `volunteer_cards = personal_kort`, ...), but every query still reads Norwegian columns and re-labels them per query, e.g. `volunteer_cards.c.kortnummer.label("primary_text")` in `app/domain/volunteers/repository.py`. The translation cost is paid on every new query forever until the database is renamed.

- Observation: Alembic has no baseline. The migration chain in `migrations/versions/` starts at `20260313_1015_initial_auth_support.py`, which assumes the copied legacy schema already exists. The repo's own agent guidance warns "Production schema may diverge from migrations — verify columns exist before deploying schema-dependent code." The SQLAlchemy table definitions only declare the columns the app uses, so production tables almost certainly carry additional legacy columns not visible anywhere in this repository.

- Observation: There is no CI. `.github/workflows/` does not exist. `sonar-project.properties` exists for SonarQube, but nothing runs tests, `openapi-check`, or migrations on push.

- Observation: The deprecated mobile API is still served. `app/api/legacy/mobile_card.py` adapts `POST /api/DigitalInternkort/RequestAccessTokenOnEmail` and `POST /api/DigitalInternkort/GetInternkortInformation` onto the mobile-card service. The legacy .NET backend it existed to mirror was declared archive-safe on 2026-05-05 (`docs/issues/current-documentation-issues.md`), and `kvarteret-internbevis-rn` defaults to `/api/v1/mobile-card`. What is not yet proven is that no installed app version still calls the old paths.

- Observation: `frontend-eventside` is the only client that touches the database by table name (via supabase-js string queries), and it touches only the event tables (`events`, `event_types`, `event_organizer_groups`, `event_organizer_group_memberships`, `rooms`). Those tables are already English and are not renamed by this plan, so the M2 rename does not affect `frontend-eventside`. The other clients (`kvarteret-internbevis-rn`, `samfunnetibergen`) speak only HTTP to this app.

- Observation: A few type-level defects survive in otherwise-new tables: `events.updated_at` is `DateTime` without timezone and nullable, while every sibling column is `timestamptz`; `grupper.id_overgruppe` and `registrering_gruppe_medlem.droppet_av_user_id` lack foreign keys; `historie_kurs.gjennomfort_dato` is an `Integer` semester code misleadingly named "dato" (date).

- Observation: The volunteer domain modules have outgrown the file-size guidance. `app/domain/volunteer_applications/` is 2,352 lines and `app/domain/volunteers/` is 2,318 lines. ADR-001 already prescribes the fix (workflow coordinator + read/write split) and lists "extract volunteer role assignments into their own domain module" as a follow-up.

## Decision Log

- Decision: Database tables are renamed to exactly the Python alias names that already exist in `app/db/table_defs/__init__.py` (e.g. `personal` → `volunteer_records`, `personal_kort` → `volunteer_cards`, `kurs` → `courses`).
  Rationale: The codebase already chose its English vocabulary; reusing it means the rename deletes the alias layer with near-zero churn in repositories, services, and tests. Inventing "better" names now would force a second rename through 18k lines of code.
  Date/Author: 2026-06-10 / Claude

- Decision: The rename cutover uses a short announced maintenance window (apply migration, then promote the already-built Vercel deployment), not dual-name compatibility views.
  Rationale: This is an internal admin tool plus a mobile API whose clients retry; Kvarteret owns all consumers. A few minutes of degraded service is cheaper and safer than maintaining a view layer with `INSTEAD OF` triggers for writes, which would have to be built and torn down for one cutover.
  Date/Author: 2026-06-10 / Claude

- Decision: `/api/DigitalInternkort/*` removal is gated on observed traffic, not on a calendar date. M3 first adds explicit hit logging, then removes the routes only after four consecutive weeks of zero non-synthetic traffic.
  Rationale: The endpoints exist solely for old installed app versions. Traffic is the only honest signal that they are gone; the boundary doc (`docs/reference/api-boundaries.md`) already mandates exactly this gate.
  Date/Author: 2026-06-10 / Claude

- Decision: The April mobile-card feature (`mobile_card_april_state`, `app/domain/mobile_card/april_state.py`) is kept.
  Rationale: It is a small, recently built, deliberately seasonal feature with admin UI wiring, not .NET-era baggage. Removing it is product cleanup, not migration cleanup, and is out of scope here.
  Date/Author: 2026-06-10 / Claude

- Decision: Bringing `frontend-eventside` event writes through this backend's API stays out of scope.
  Rationale: It is a real architectural gap (tracked in `docs/issues/current-documentation-issues.md`), but it is new feature work with its own auth design, not legacy restructuring. Mixing it in would balloon this plan. The event tables are untouched by M2 precisely so that decision stays independent.
  Date/Author: 2026-06-10 / Claude

- Decision: Extra production columns discovered by the M0 audit that no code reads are dropped in M2, each with its own line in this Decision Log naming the column and the evidence it is unused.
  Rationale: "We are the only consumer" makes unused-column retention pure liability; but each drop must be individually evidenced and recorded so the plan remains the audit trail.
  Date/Author: 2026-06-10 / Claude

## Outcomes & Retrospective

To be written as milestones complete.

## Context and Orientation

The working directory is the repository root of `kvarteret-personal`. It is a FastAPI "modular monolith": HTTP routes in `app/web/routes/{feature}/` (server-rendered HTMX admin UI) and `app/api/v1/` (JSON), domain logic in `app/domain/{feature}/` (each with `models.py`, `repository.py`, `service.py`, sometimes `workflow.py`), SQLAlchemy Core table objects in `app/db/table_defs/`, and the object graph wired in `app/runtime.py`. Alembic migrations live in `migrations/versions/` named `YYYYMMDD_HHMM_description.py`. The production database is Supabase Postgres; the app deploys to Vercel from `api/index.py`. The checked-in `openapi.json` is the API contract that sibling repos generate clients from; regenerate it with `make openapi` and verify with `make openapi-check`.

Three terms of art used below:

- "Alias layer": the block of plain Python assignments at the bottom of `app/db/table_defs/__init__.py` that gives Norwegian-named `Table` objects English Python names, e.g. `volunteer_records = personal`. It renames tables in Python only; column names stay Norwegian everywhere.
- "Baseline migration": an Alembic revision that records the complete pre-existing schema as the starting point of the chain, so that `alembic upgrade head` on an empty database produces a faithful copy of production. Today no such revision exists; the chain assumes the legacy schema is already present.
- "Supabase development branch": Supabase's database branching feature, which clones the production schema (and optionally data) into a disposable instance. All destructive migrations in this plan are rehearsed on a branch before production.

The full rename map (current name → new name) that M2 implements:

    personal                    -> volunteer_records
    personal_bilde              -> volunteer_photos
    personal_kort               -> volunteer_cards
    paarorende                  -> volunteer_next_of_kin
    grupper                     -> groups
    verv                        -> assignment_roles
    historie                    -> role_assignments
    kurs                        -> courses
    historie_kurs               -> course_completions
    grupper_kurs_kobling        -> group_course_requirements
    registrering                -> volunteer_application_invites
    nytt_personal               -> volunteer_application_submissions
    registrering_gruppe         -> volunteer_application_groups
    registrering_gruppe_medlem  -> volunteer_application_group_members

Column renames (Norwegian → English), applied with the table renames. Columns already in English (`source`, `status`, `token`, `filename`, ...) keep their names. The audit in M0 may extend this list:

    fornavn          -> first_name        etternavn       -> last_name
    epost            -> email             telefon         -> phone
    fodselsdato      -> birth_date        kjonn           -> gender
    gateadresse      -> street_address    postnummerid    -> postal_code
    opprettet        -> created_at        navn            -> name
    beskrivelse      -> description       aktiv           -> is_active
    aktiv_til_og_med -> active_through_semester
    id_overgruppe    -> parent_group_id   rabatt_trinn    -> discount_tier
    id_personal      -> volunteer_id      id_gruppe       -> group_id
    id_verv          -> role_id           id_kurs         -> course_id
    verv (column)    -> name              pingvinpoeng    -> penguin_points
    signert_kontrakt -> contract_signed   gjennomfort_dato -> completed_semester
    kortnummer       -> card_number
    internkortaccesstoken              -> mobile_card_access_token
    internkort_access_token_created_at -> mobile_card_access_token_created_at
    gruppe_id        -> group_id          registrering_id -> invite_id
    registrering_epost -> applicant_email rolle           -> role
    droppet          -> dropped_at        droppet_av_user_id -> dropped_by_user_account_id

Tables dropped outright (M1): `aspnetusers`, `aspnetroles`, `aspnetuserroles`, `grupper_admin_kobling`, `personal_fil`. Dropped in M3 after the bridge audit: `auth_migration_events` and the `user_accounts.legacy_user_id` column. Tables untouched: the event tables (`events` apart from its `updated_at` type fix, `event_types`, `event_organizer_groups`, `event_organizer_group_memberships`, `rooms`), `user_accounts`, `group_admin_memberships` (its `gruppe_id` column is renamed to `group_id`), `web_sessions`, `integration_tokens`, `mobile_card_april_state`.

## Plan of Work

### M0 — Schema baseline and drift audit

Capture the truth before changing it. Dump the full production schema (`pg_dump --schema-only` via the Supabase session pooler) and commit it under `docs/reference/schema-snapshots/<date>-pre-restructure.sql` as the audit artifact. From the dump, produce an inventory of every table, column, index, constraint, RLS policy, trigger, view, and function in `public`, and diff it three ways: against `app/db/table_defs/`, against the cumulative effect of `migrations/versions/`, and against the rename map above. Every object that exists in production but in neither code nor migrations gets a disposition (keep-and-define, rename, or drop) recorded in the Decision Log before M1 begins.

Then create the baseline: a new first Alembic revision `migrations/versions/<stamp>_baseline_legacy_schema.py` that creates the full pre-restructure schema, re-parented so the existing chain follows it (`20260313_1015_initial_auth_support` gets `down_revision` pointing at the baseline). Production is already at head, so the baseline is stamped, never executed there; its purpose is that `alembic upgrade head` on an empty Postgres now reproduces production. Prove exactly that against a local disposable Postgres, and make it the CI invariant in M5.

Also verify Supabase point-in-time recovery is active (or take a manual `pg_dump` data dump) so every later destructive step has a rollback path.

### M1 — Drop dead legacy structures

One migration, `<stamp>_drop_dead_legacy_tables.py`, that drops `aspnetusers`, `aspnetroles`, `aspnetuserroles`, `grupper_admin_kobling`, and `personal_fil` — each preceded by a guard query proving the audit's "unused" claim still holds. Before dropping the aspnet tables, export their rows to a private archive location outside this public repository (they contain the historical admin list and 66 password hashes); record the archive location in the Decision Log. Remove the corresponding `Table` definitions and aliases (`volunteer_documents`, `group_hierarchy`) from `app/db/table_defs/` and `app/db/tables.py`. Rehearse on a Supabase development branch, run `make test`, apply to production. This milestone is deliberately small and independently shippable: it proves the branch-rehearse-apply loop works before the big rename.

### M2 — Rename the database to English and fix column types

One migration, `<stamp>_rename_schema_to_english.py`, containing only `ALTER TABLE ... RENAME TO ...` and `ALTER TABLE ... RENAME COLUMN ...` statements per the rename map, plus the type fixes: `events.updated_at` to `timestamptz NOT NULL DEFAULT now()` (backfill nulls from `created_at`), a foreign key from `groups.parent_group_id` to `groups.id`, a foreign key from `volunteer_application_group_members.dropped_by_user_account_id` to `user_accounts.id` (validate existing data first; use `NOT VALID` plus `VALIDATE CONSTRAINT` if any orphans need cleanup), and renames of any constraint or index whose name embeds an old table name (`uq_registrering_token`, the `ck_registrering_gruppe_medlem_*` checks, the pg_trgm indexes from `20260313_1545`, the live-query indexes from `20260316_1500`). Postgres rewrites stored references (views, RLS policies, triggers, functions) automatically on rename, but the M0 inventory of policies must be re-checked afterward on the branch — `pg_policies` should show the same policy count with updated table references.

In the same commit, rewrite `app/db/table_defs/public.py` so the `Table` objects carry the English names natively, delete the alias block from `app/db/table_defs/__init__.py`, and sweep the repositories: every `volunteer_cards.c.kortnummer`-style Norwegian column access becomes the English column, and per-query `.label("...")` translations that existed only to anglicize output are removed. The Jinja templates and Pydantic models already speak English, so the sweep is mechanical; `make test` (226 tests, all using fake repositories or the SQLAlchemy expressions directly) is the safety net, and `make openapi-check` proves the public contract did not move. Update the scripts that touch renamed tables (grep `scripts/` for old names; at minimum `scripts/normalize_phone_numbers.py` and `scripts/bootstrap_auth_user.py`).

Cutover, rehearsed end-to-end on a Supabase development branch first: announce the window; `vercel deploy` the new code as a preview deployment; run `alembic upgrade head` against production through the session pooler; immediately promote the deployment to production; run the smoke checks (`/health`, login, volunteer list, `POST /api/v1/mobile-card/access-codes` with a known email, `/api/now-playing`). The window between migration and promotion is the only downtime; measured on the branch rehearsal it should be well under a minute (renames are metadata-only and take milliseconds; the window is deploy-promotion latency). Rollback within the window is `alembic downgrade -1` (the migration is pure renames, so the downgrade is exact) plus leaving the old deployment in place.

### M3 — Retire the legacy DigitalInternkort API and auth-bridge vestiges

First instrument: add a structured log line (event `legacy.digital_internkort.hit`, with user agent) to both handlers in `app/api/legacy/mobile_card.py`, deploy, and watch Vercel logs. After four consecutive weeks of zero non-synthetic hits, delete `app/api/legacy/`, its registration in `app/api/router.py`, the two `/api/DigitalInternkort/*` entries from `openapi.json` via `make openapi`, and the legacy-shape tests. Simultaneously retire the bridge vestiges: rename `LoginService.login_with_bridge` to `login`, drop `legacy_user_id` from `app/auth/models.py`, `app/auth/repository.py`, and `app/domain/admin_accounts/service.py`, and ship migration `<stamp>_drop_auth_bridge_vestiges.py` dropping `auth_migration_events` and `user_accounts.legacy_user_id` (export `auth_migration_events` to the private archive first — it is the only record of how each admin account was migrated). The instrumentation can be deployed the same day M0 starts; the clock runs while M1–M2 proceed.

### M4 — Code restructure to match ADR-001

With the database speaking the domain language, finish the module shape that ADR-001 prescribes. Extract role assignments (the `role_assignments` queries and the semester-transfer flow) out of `app/domain/volunteers/` into `app/domain/role_assignments/` with its own `models.py`, `repository.py`, `service.py` — this is the ADR's explicitly listed follow-up. Then split the two oversized modules along the ADR's read/write line: `volunteers` gets a `queries.py` for the list/search/detail read models (mirroring `groups/queries.py`), leaving `service.py` with writes; `volunteer_applications` keeps `workflow.py` as the coordinator and moves its read-model methods the same way. Wire new dependencies through `app/dependencies.py` and `app/runtime.py`; move the corresponding tests under `tests/unit/domain/` and `tests/web/`. No behavior changes: this milestone is accepted purely by the existing suite staying green and by file sizes — no `app/domain/{feature}` directory above ~1,200 lines, no single service module above ~800.

### M5 — CI pipeline and schema-drift guardrails

Create `.github/workflows/ci.yml` running on every push and PR: `uv sync`, `uv run pytest` (the suite needs no database), `make openapi-check`, and a migration job that starts a disposable Postgres service container and runs `alembic upgrade head` from empty — proving the baseline plus chain stays applicable forever. Add `ruff` with a checked-in config to `pyproject.toml` and the workflow (start with default rules plus import sorting; fix or `noqa` the initial findings in a dedicated commit). Add a small drift-check script, `scripts/check_schema_drift.py`, that connects to a database, reflects `public`, and diffs it against `app/db/table_defs/` metadata (tables and columns the app declares must exist with matching types); run it in CI against the migrated container, and document in `docs/how-to/` how to run it against production when diagnosing incidents. Finally update the documentation set: `docs/explanation/kvarteret-personal-architecture.md` (drop the legacy-surface paragraphs once M3 lands), `docs/reference/api-boundaries.md` (remove the deprecated boundary section), and the skill/agent notes that warn about schema divergence — after M0/M5 that warning is replaced by "run the drift check".

## Concrete Steps

All commands run from the repository root unless stated otherwise.

Capture the production schema (M0):

    pg_dump "$DATABASE_URL" --schema-only --schema=public --no-owner --no-privileges \
      > docs/reference/schema-snapshots/$(date +%Y%m%d)-pre-restructure.sql

Create and rehearse a migration on a Supabase development branch (M1, M2, M3): create the branch in the Supabase dashboard or MCP tooling, point `DATABASE_URL` in a local `.env.branch` at the branch's pooler, then:

    uv run alembic upgrade head
    uv run pytest -q
    uv run python scripts/check_schema_drift.py   # exists from M5 onward

Prove the baseline reproduces production on an empty database (M0, then CI forever):

    docker run -d --name pg-baseline -e POSTGRES_PASSWORD=x -p 55432:5432 postgres:17
    DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:55432/postgres uv run alembic upgrade head
    pg_dump postgresql://postgres:x@localhost:55432/postgres --schema-only --schema=public --no-owner --no-privileges \
      > /tmp/baseline-replay.sql

(Compare `/tmp/baseline-replay.sql` against the committed snapshot with `apgdiff` or a normalizing diff script; raw `diff` is too noisy. The acceptance bar is zero structural differences.)

Production cutover (M2), in order, inside the announced window:

    vercel deploy                       # build the rename-aware code as a preview
    uv run alembic upgrade head         # against production DATABASE_URL
    vercel promote <deployment-url>     # promote immediately after migration succeeds
    curl -fsS https://personal.kvarteret.no/health

After any API-surface change (M3):

    make openapi && make openapi-check

Run the full verification battery after each milestone:

    make test
    uv run pytest tests/api/ tests/web/ tests/unit/ -q

## Validation and Acceptance

M0 is accepted when the schema snapshot file is committed, every production-only object has a Decision Log disposition, and `alembic upgrade head` on an empty Postgres produces a schema structurally identical to the snapshot.

M1 is accepted when `\dt public.*` on production no longer lists `aspnetusers`, `aspnetroles`, `aspnetuserroles`, `grupper_admin_kobling`, or `personal_fil`; the private archive export of the aspnet rows exists; and `make test` passes with the table definitions removed.

M2 is accepted when production contains only English table and column names from the rename map; logging in to `personal.kvarteret.no`, opening a volunteer detail page, and fetching a mobile card via `POST /api/v1/mobile-card/sessions` all work; `make openapi-check` shows no contract drift; and `grep -rn "fornavn\|etternavn\|kortnummer\|grupper\b" app/` returns no hits outside migration files.

M3 is accepted when the Vercel logs show four weeks of zero non-synthetic `legacy.digital_internkort.hit` events before removal, `POST /api/DigitalInternkort/RequestAccessTokenOnEmail` returns 404 in production afterward, `openapi.json` no longer mentions DigitalInternkort, and `user_accounts` has no `legacy_user_id` column.

M4 is accepted when `app/domain/role_assignments/` exists and owns semester-transfer plus role-history logic, no domain directory exceeds ~1,200 lines (`find app/domain/* -name '*.py' | xargs wc -l`), and the full suite passes unchanged in behavior.

M5 is accepted when a PR that breaks a test, stales `openapi.json`, or breaks the migration chain fails CI visibly on GitHub, and `scripts/check_schema_drift.py` exits zero against the CI-migrated container and against production.

## Idempotence and Recovery

Every migration in this plan is rehearsed on a Supabase development branch before production, and production is only touched after a verified PITR window or manual dump exists. M1 and M3 drops are preceded by archival exports; recovery is restoring the export. The M2 rename migration is symmetric — its `downgrade()` renames everything back, so recovery inside the window is `alembic downgrade -1` plus keeping the previous Vercel deployment live (do not delete it until the smoke checks pass). The baseline revision is stamped, never executed, on production; re-running `alembic upgrade head` is always a no-op when current. Code changes ship behind the existing test suite; any milestone can stop and hold indefinitely without leaving the system in a mixed state, because each milestone ends with code and schema agreeing.

## Artifacts and Notes

Current measured state (2026-06-10), the "before" picture:

    app python LOC: 18,388   tests LOC: 8,099   tests collected: 226
    domain module sizes: volunteer_applications 2,352  volunteers 2,318
                         groups 1,066  mobile_card 1,056
    migrations: 24 revisions, no baseline
    dead tables in prod: aspnetusers (66 rows historically), aspnetroles,
                         aspnetuserroles, grupper_admin_kobling, personal_fil (88 rows)
    deprecated API: 2 DigitalInternkort operations in openapi.json
    CI: none (.github/workflows absent); Sonar config present

## Interfaces and Dependencies

No new runtime dependencies. Tooling additions: `ruff` (dev dependency, M5), `apgdiff` or an equivalent schema-diff approach (M0, may be a small script instead), GitHub Actions with a `postgres:17` service container (M5).

At the end of M2, `app/db/table_defs/public.py` defines `Table` objects whose SQL names equal their Python names — `volunteer_records`, `volunteer_photos`, `volunteer_cards`, `volunteer_next_of_kin`, `groups`, `assignment_roles`, `role_assignments`, `courses`, `course_completions`, `group_course_requirements`, `volunteer_application_invites`, `volunteer_application_submissions`, `volunteer_application_groups`, `volunteer_application_group_members` — and `app/db/table_defs/__init__.py` contains imports only, no aliases.

At the end of M3, `app/auth/login_service.py` exposes:

    class LoginService:
        async def login(self, *, identifier: str, password: str,
                        ip_address: str | None, user_agent: str | None) -> LoginResult

At the end of M4, `app/domain/role_assignments/` exposes a `RoleAssignmentsService` wired through `app/dependencies.py` and `app/runtime.py`, owning role history reads and the semester-transfer preview/apply flow previously inside `VolunteersService`.

Revision note: Initial version, authored from the 2026-06-10 research pass over the working tree at branch `claude/silly-curie-59fb1f`. No implementation has started; the Progress section reflects research only.
