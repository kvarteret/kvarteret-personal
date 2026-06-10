# Finish the .NET-era cleanup and restructure the codebase: baseline the schema, drop dead legacy structures, rename the database to English, retire the legacy mobile API, rebuild the data-access layer, enforce modular-monolith boundaries with owned tables, and make the volunteer application lifecycle an explicit state machine

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `/PLANS.md` at the repository root.

## Purpose / Big Picture

`kvarteret-personal` replaced a legacy ASP.NET 8 backend ("Personaldatabase_Backend") and its Angular frontend. The replacement is live at `personal.kvarteret.no`, but the migration was deliberately conservative: the Supabase Postgres database still carries the legacy Norwegian schema copied from the .NET app (`personal`, `grupper`, `historie`, `verv`, `kurs`, ...), the dead ASP.NET Identity tables (`aspnetusers`, `aspnetroles`, `aspnetuserroles`), a deprecated compatibility API (`/api/DigitalInternkort/*`), and a Python alias layer that papers over the naming gap (`volunteer_cards = personal_kort`). There is no Alembic baseline of the inherited schema and no CI pipeline. Beyond the legacy debt, the layers above the database accumulated their own friction during the fast rewrite: repositories return untyped dicts that a hand-written mapper layer re-keys into models, every repository call opens its own database connection, transaction mechanics leak into services, and the volunteer application lifecycle — the most important business process in the system — is encoded as string literals scattered across two thousand lines.

Kvarteret is the only consumer of this system. All clients (`kvarteret-internbevis-rn`, `samfunnetibergen`, `frontend-eventside`) are owned by the same organization, so the database may be migrated and modified at will, provided the cutovers documented here are followed.

The governing values for this plan, in order: the repository must be concise; business logic must be easy to navigate (the volunteer application lifecycle should be readable from one file, per ADR-001); and every change must be independently shippable behind the test suite.

After this plan is complete:

- The database speaks the same English domain language as the code, every dead legacy structure is gone, and `/api/DigitalInternkort/*` is removed (gated on measured zero traffic).
- Alembic has a true baseline, and CI proves on every push that tests pass, `openapi.json` is current, and the migration chain applies from empty to head.
- One database session serves one HTTP request; repositories return typed rows; the mapper layer is deleted; services no longer manage transactions.
- Each domain module owns its tables. Writes to a table happen only in its owning module; cross-module reads happen only in declared read models; the rules are machine-enforced by import-linter in CI, not by convention.
- The volunteer application lifecycle is a real state machine: all states and transitions live in one pure module with an exhaustive test matrix, the database enforces the state vocabulary with check constraints, and the group-approval hardening from the group-registration ADR (atomic group approval, no per-person approval for active grouped members) is implemented.

A reader can verify the end state by running `make test` and `make lint-imports` (green), `make openapi-check` (clean), inspecting the database with `\dt public.*` (English names only), grepping the domain layer for application-status string literals (matches only in `state_machine.py`), and requesting `POST /api/DigitalInternkort/RequestAccessTokenOnEmail` (404).

## Progress

- [x] (2026-06-10) Research pass 1: schema inventory, dead-table audit, API surface audit, client boundary audit, CI audit.
- [x] (2026-06-10) Research pass 2: data-access layer audit (base repository, session lifecycle, mapper layer, transaction usage in services) and state-machine audit of `volunteer_applications` (status vocabulary, transition sites, group-registration ADR follow-ups). Findings in `Surprises & Discoveries`.
- [ ] M0: Schema baseline and drift audit.
- [ ] M1: CI pipeline and guardrails (pulled forward — it protects every later milestone).
- [ ] M2: Drop dead legacy structures.
- [ ] M3: Rename the database to English and fix column types.
- [ ] M4: Retire the legacy DigitalInternkort API and auth-bridge vestiges (traffic-gated; runs in parallel from M0 onward).
- [ ] M5: Data-access overhaul — request-scoped unit of work, typed rows, delete the mapper layer, repository contracts.
- [ ] M6: Modular monolith with owned tables — ownership map, import-linter boundaries, module extractions and splits.
- [ ] M7: Volunteer application state machine — pure transitions module, database constraints, atomic group approval.

## Surprises & Discoveries

Findings from the research passes (2026-06-10). Update as implementation reveals more.

- Observation: The legacy ASP.NET Identity tables are dead code. `aspnetusers`, `aspnetroles`, and `aspnetuserroles` are defined in `app/db/table_defs/public.py` but nothing queries them. Migration `20260319_1215_drop_unused_legacy_identity_tables.py` already dropped the empty claims/logins/tokens tables and `__efmigrationshistory`, but kept these three.
  Evidence: `grep -rn "aspnet" app --include='*.py'` matches only `table_defs` and `tables.py`.

- Observation: Login no longer touches legacy password hashes. `app/auth/login_service.py` authenticates directly against Supabase Auth; the method is still named `login_with_bridge` but contains no bridge. `user_accounts.legacy_user_id` and `auth_migration_events` are write-only vestiges.

- Observation: `grupper_admin_kobling` is unused (replaced by `group_admin_memberships`), and its alias `group_hierarchy` in `app/db/table_defs/__init__.py` is a misnomer — group hierarchy actually lives in `grupper.id_overgruppe`.

- Observation: `personal_fil` is dead. The documents feature was removed (commit `13d26ad`, ADR-001 "Cleanup Decisions"), and a web test asserts the routes are gone. The table and its `volunteer_documents` alias remain defined.

- Observation: The Python alias layer translates table names but not columns. Every query still reads Norwegian columns and re-labels per query, e.g. `volunteer_cards.c.kortnummer.label("primary_text")` in `app/domain/volunteers/repository.py`.

- Observation: Alembic has no baseline. The chain starts at `20260313_1015_initial_auth_support.py`, which assumes the copied legacy schema already exists. The SQLAlchemy table definitions only declare the columns the app uses, so production tables almost certainly carry additional legacy columns not visible anywhere in this repository.

- Observation: There is no CI. `.github/workflows/` does not exist. `sonar-project.properties` exists, but nothing runs tests, `openapi-check`, or migrations on push.

- Observation: The deprecated mobile API is still served. `app/api/legacy/mobile_card.py` adapts two `/api/DigitalInternkort/*` endpoints onto the mobile-card service. The legacy backend it mirrored was declared archive-safe on 2026-05-05, but no measurement proves installed app versions have stopped calling the old paths.

- Observation: `frontend-eventside` is the only client that touches the database by table name (supabase-js string queries), and only the event tables. Those are already English and not renamed by this plan. The other clients speak only HTTP to this app.

- Observation: Type-level defects in otherwise-new tables: `events.updated_at` is nullable `DateTime` without timezone; `grupper.id_overgruppe` and `registrering_gruppe_medlem.droppet_av_user_id` lack foreign keys; `historie_kurs.gjennomfort_dato` is an `Integer` semester code misleadingly named "dato".

- Observation: Every repository call opens its own database session, and production uses `NullPool` (`app/db/session.py`), so each call is a fresh connection to the Supabase pooler. A request composing three repository calls pays three connection setups; the original rewrite plan already measured remote round trips as the latency floor. There is no request-level transaction: multi-step writes are atomic only when routed through `SqlAlchemyRepository.execute_in_transaction(callback)`.
  Evidence: every `fetch_*` helper in `app/db/repository.py` wraps `async with self.session_factory() as session`.

- Observation: Transaction mechanics leak into services. `groups/service.py` and `courses/service.py` call `self.execute_in_transaction(callback)` directly — the service layer owns SQL session management in exactly the places where multi-step writes matter.
  Evidence: `grep -rn "execute_in_transaction" app/domain` matches `groups/service.py` (5 sites), `courses/service.py` (2), `spotify/repository.py`, `mobile_card/april_state.py`.

- Observation: Repositories return `dict[str, Any]` and a hand-written mapper layer re-keys them into Pydantic models with string indexing (`row["fornavn"]` in `app/domain/volunteers/mappers.py`). The workflow protocols in `app/domain/volunteer_applications/workflow.py` have given up on typing entirely (`-> tuple[Any, int]`, `detail: Any`). After the M3 rename, dict keys match model fields almost one-to-one, so most of this layer becomes deletable.

- Observation: Services construct their own repositories as hidden defaults (`repository or VolunteersRepository()` in `VolunteersService.__init__`), producing repositories with no session factory that raise `RuntimeError` on first use. All real wiring already goes through `app/runtime.py`.

- Observation: Presentation leaks into the query layer. `app/domain/groups/queries.py` imports `build_photo_media_url` and semester label formatting — read-model queries mint signed media URLs and display strings.

- Observation: The volunteer application lifecycle is a de facto state machine encoded as scattered string literals. Application states `prospect`, `invited`, `submitted`, `promoted`, `rejected` and membership states `active`, `dropped` appear as inline strings at 14+ sites across `volunteer_applications/repository.py` and `service.py` (995 and 1,090 lines respectively). No single file states which transitions are legal. The database does not constrain `registrering.status` at all (plain `Text`); only the membership table has check constraints.
  Evidence: `grep -rno "status.*['\"][a-z_]*['\"]" app/domain/volunteer_applications/*.py` — matches in repository.py lines 74, 105, 130, 152, 189, 622, 655, 693, 803, 834, 837 and service.py lines 139, 874, 957.

- Observation: The group-registration ADR (`docs/explanation/group-volunteer-registration-adr.md`) carries an explicit unimplemented hardening list: block per-person approval for active grouped applications, make group approval atomic and all-or-nothing, group the admin list by `group_id`, and add tests for grouped approval and partial states. These are state-machine concerns and are absorbed into M7.

- Observation: The mobile-card module's persistent state lives as columns on the volunteers table (`personal.internkortaccesstoken`, `personal.internkort_access_token_created_at`), a .NET-era denormalization that breaks table ownership: the mobile-card module writes the volunteers module's table.

- Observation: The volunteer domain modules have outgrown the file-size guidance: `volunteer_applications` 2,352 lines, `volunteers` 2,318. ADR-001 already prescribes the read/write split and lists extracting role assignments as a follow-up.

## Decision Log

- Decision: Database tables are renamed to exactly the Python alias names that already exist in `app/db/table_defs/__init__.py` (e.g. `personal` → `volunteer_records`, `kurs` → `courses`).
  Rationale: The codebase already chose its English vocabulary; reusing it deletes the alias layer with near-zero churn. Inventing better names now would force a second rename through 18k lines.
  Date/Author: 2026-06-10 / Claude

- Decision: The rename cutover uses a short announced maintenance window (apply migration, promote the pre-built Vercel deployment), not dual-name compatibility views.
  Rationale: Internal tool, organization owns all consumers; minutes of degraded service are cheaper than building and tearing down an updatable-view layer for one cutover.
  Date/Author: 2026-06-10 / Claude

- Decision: `/api/DigitalInternkort/*` removal is gated on observed traffic (four consecutive weeks of zero non-synthetic hits after instrumentation), not a calendar date.
  Rationale: Traffic is the only honest signal that old installed app versions are gone; `docs/reference/api-boundaries.md` already mandates this gate.
  Date/Author: 2026-06-10 / Claude

- Decision: The April mobile-card feature is kept; bringing `frontend-eventside` event writes through this backend stays out of scope.
  Rationale: The first is recent product work, not legacy debt. The second is new feature work with its own auth design, tracked separately in `docs/issues/current-documentation-issues.md`; the event tables are untouched by this plan precisely so that decision stays independent.
  Date/Author: 2026-06-10 / Claude

- Decision: Extra production columns discovered by the M0 audit that no code reads are dropped in M3, each with its own Decision Log line naming the column and the evidence.
  Rationale: Sole-consumer status makes unused-column retention pure liability, but each drop must be individually evidenced.
  Date/Author: 2026-06-10 / Claude

- Decision: CI (originally the last milestone) is pulled forward to M1, immediately after the baseline exists.
  Rationale: M5–M7 are large behavior-preserving refactors. Doing them without a pipeline that runs the suite, the OpenAPI check, and a migration replay on every push would be negligent; the baseline from M0 is the only prerequisite CI needs.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: The target architecture is a modular monolith with owned tables and shared read models — not microservices, not full hexagonal architecture, not CQRS/event sourcing, and not strict table isolation for reads.
  Rationale: Considered alternatives. Microservices: rejected — one small team, one database, one deployment; ADR-001 already forbids distributed infrastructure without a concrete reliability requirement. Full hexagonal (ports/adapters for everything): rejected — the app already has the only ports that pay rent (repository protocols, infrastructure adapters); ceremonial ports for HTTP and templates would add files without adding navigability, violating the conciseness requirement. CQRS with separate write/read stores or event sourcing: rejected — the audit requirements here are timestamps and a registration log, fully served by columns; event sourcing would make the most important business flow harder to read, the opposite of the goal. Strict table isolation even for reads (each module may only query its own tables, composing cross-module data in Python): rejected — admin pages like the group detail join volunteers, photos, role assignments, and positions in one SQL statement with JSON aggregates because round trips to the remote Supabase database are the measured latency floor; forcing per-module queries would reintroduce the serial-query latency the rewrite explicitly engineered away. What remains is the honest version of "tables are isolated": every table has exactly one owning module, only the owning module's repository may write it, cross-module reads are allowed only inside dedicated read-model modules (`queries.py`) that may import other modules' table definitions but never their services, and cross-module writes go through the owning module's service. The boundary is enforced by import-linter in CI, so it is a build failure, not a convention.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: Table definitions move from the central `app/db/table_defs/public.py` into the owning domain modules (`app/domain/{module}/tables.py`); `app/db/` keeps only the shared `MetaData`, the auth/storage schema reflections, and the engine/session machinery.
  Rationale: This makes ownership physical, not documentary: importing another module's tables is visible in the import graph, which is exactly what import-linter checks. The shared `MetaData` object keeps Alembic autogeneration and cross-module read-model joins working unchanged.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: Mobile-card access tokens move out of `volunteer_records` into a new `mobile_card_access_codes` table owned by the mobile-card module (columns: `volunteer_id` PK/FK, `code_hash`, `created_at`).
  Rationale: It is the single ownership violation that survives the rename — the mobile-card module writing the volunteers table. A dedicated table fixes ownership, removes two nullable columns from the hottest table, and costs one small data-copy migration.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: Database access uses a request-scoped unit of work: one `AsyncSession` per HTTP request, injected via FastAPI dependency; repositories receive the session and never create their own; the dependency commits on success and rolls back on exception. `execute_in_transaction` and the session-per-method helpers are deleted.
  Rationale: Under `NullPool` on Vercel, session-per-repository-call means connection-per-repository-call against a remote pooler — measured as the dominant latency cost during the rewrite. A request-scoped session makes multi-step writes atomic by default (the state machine in M7 and the atomic group approval depend on this), removes the callback-style transaction API, and pulls transaction mechanics out of services.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: Repositories return typed rows (Pydantic models validated at the repository boundary, or frozen dataclasses for internal read models), not `dict[str, Any]`. The hand-written mapper layer is deleted except where real derivation happens (full-name building, semester labels, gender labels). Workflow protocols replace every `Any` with the real model type.
  Rationale: After M3 the database columns equal the model field names, so `Model.model_validate(row)` does what `mappers.py` does today, with static checking. Stringly-typed row access is the largest remaining class of runtime-only failure.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: The volunteer application lifecycle is encoded as a pure, exhaustively tested state machine in one module: a `StrEnum` of states, an explicit transition table, and a `transition()` function with no I/O. The database enforces the state vocabulary with check constraints. State remains a column; there is no event sourcing and no workflow engine.
  Rationale: The lifecycle is the system's most important business logic and is currently unreadable-by-scattering. A pure transition module is the smallest construct that makes "what can happen next" a fact you can read and test rather than reverse-engineer from SQL call sites. ADR-001's instruction that the lifecycle "should be readable from one file" becomes literally true.
  Date/Author: 2026-06-10 / Claude (revision 2)

## Outcomes & Retrospective

To be written as milestones complete.

## Context and Orientation

The working directory is the repository root of `kvarteret-personal`. It is a FastAPI modular monolith: HTTP routes in `app/web/routes/{feature}/` (server-rendered HTMX admin UI) and `app/api/v1/` (JSON), domain logic in `app/domain/{feature}/`, SQLAlchemy Core table objects in `app/db/table_defs/`, the object graph wired in `app/runtime.py` with FastAPI `Depends()` factories in `app/dependencies.py`. Alembic migrations live in `migrations/versions/` named `YYYYMMDD_HHMM_description.py`. The production database is Supabase Postgres; the app deploys to Vercel from `api/index.py`. The checked-in `openapi.json` is the API contract sibling repos generate clients from (`make openapi` / `make openapi-check`). ADR-001 (`docs/adr/001-modular-monolith-event-bus.md`) fixes the architectural style: pragmatic modular monolith, explicit workflow coordinators for stateful processes, no distributed infrastructure.

Terms of art used below:

- "Alias layer": the block of assignments at the bottom of `app/db/table_defs/__init__.py` giving Norwegian-named `Table` objects English Python names (`volunteer_records = personal`). Table names only; columns stay Norwegian.
- "Baseline migration": an Alembic revision recording the complete pre-existing schema as the start of the chain, so `alembic upgrade head` on an empty database reproduces production. Does not exist today.
- "Supabase development branch": Supabase's database branching feature cloning production schema into a disposable instance. Every destructive migration in this plan is rehearsed on a branch first.
- "Unit of work": one database session whose lifetime equals one HTTP request, created by a FastAPI dependency, shared by every repository the request touches, committed once at the end. The opposite of today's session-per-repository-call.
- "Owned table": a table that exactly one domain module may write. Other modules may read it only inside read-model modules and must call the owning module's service to change it.
- "Import contract": a rule in an `importlinter` configuration, checked in CI, that fails the build when a module imports something its layer or ownership rules forbid.
- "State machine" (as used in M7): a `StrEnum` of states plus an explicit table of legal transitions and a pure function that applies them, in one file, with a test for every state/action pair.

The full rename map (current name → new name) that M3 implements:

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

Column renames (Norwegian → English), applied with the table renames; the M0 audit may extend this list:

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
    internkortaccesstoken              -> (moves to mobile_card_access_codes in M6)
    internkort_access_token_created_at -> (moves to mobile_card_access_codes in M6)
    gruppe_id        -> group_id          registrering_id -> invite_id
    registrering_epost -> applicant_email rolle           -> role
    droppet          -> dropped_at        droppet_av_user_id -> dropped_by_user_account_id

(In M3 the two internkort columns are renamed to `mobile_card_access_token` / `mobile_card_access_token_created_at` like everything else; M6 then moves them to the new table. Renaming first keeps M3 purely mechanical.)

The table ownership map that M6 makes physical and machine-enforced:

    volunteers              owns volunteer_records, volunteer_photos, volunteer_cards,
                                 volunteer_next_of_kin
    role_assignments        owns role_assignments, assignment_roles
    groups                  owns groups
    courses                 owns courses, course_completions, group_course_requirements
    volunteer_applications  owns volunteer_application_invites, _submissions,
                                 _groups, _group_members
    mobile_card             owns mobile_card_april_state, mobile_card_access_codes (new)
    events                  owns events, event_types, event_organizer_groups,
                                 event_organizer_group_memberships, rooms
    admin_accounts + auth   own  user_accounts, web_sessions, group_admin_memberships
    spotify                 owns integration_tokens
    search, feedback, stats own  no tables (read models / outbound only)

The volunteer application state machine that M7 encodes (current behavior, reconstructed from code and the group-registration ADR — verify against production data in M7 before freezing):

    states: prospect, invited, submitted, promoted, rejected
    membership states (group members): active, dropped

    prospect  --invite/submit-profile-->  submitted   (public prospect flow)
    invited   --submit-profile-------->  submitted
    invited   --resend-invitation----->  invited
    submitted --mark-trial-shift------>  submitted    (sets trial_shift_attended)
    submitted --approve--------------->  promoted     (creates volunteer record)
    submitted --reject---------------->  rejected
    any-pre-promotion --delete-------->  (row archived/removed per current rules)
    membership: active --drop--------->  dropped      (audit preserved, row kept)

Tables dropped outright (M2): `aspnetusers`, `aspnetroles`, `aspnetuserroles`, `grupper_admin_kobling`, `personal_fil`. Dropped in M4 after the bridge audit: `auth_migration_events` and `user_accounts.legacy_user_id`. Untouched: the event tables (except the `events.updated_at` type fix), `user_accounts`, `web_sessions`, `integration_tokens`, `mobile_card_april_state`.

## Plan of Work

### M0 — Schema baseline and drift audit

Capture the truth before changing it. Dump the full production schema (`pg_dump --schema-only` via the Supabase session pooler) and commit it under `docs/reference/schema-snapshots/<date>-pre-restructure.sql`. Inventory every table, column, index, constraint, RLS policy, trigger, view, and function in `public`, and diff three ways: against `app/db/table_defs/`, against the cumulative effect of `migrations/versions/`, and against the rename map above. Every production-only object gets a disposition (keep-and-define, rename, or drop) recorded in the Decision Log before M2 begins.

Create the baseline: a new first Alembic revision `<stamp>_baseline_legacy_schema.py` that creates the full pre-restructure schema, with `20260313_1015_initial_auth_support` re-parented onto it. Production is already at head, so the baseline is never executed there; its purpose is that `alembic upgrade head` on an empty Postgres reproduces production. Prove that against a local disposable Postgres. Verify Supabase point-in-time recovery is active (or take a manual data dump) so every later destructive step has a rollback path.

### M1 — CI pipeline and guardrails

Pulled forward because M5–M7 are large refactors that need the net first. Create `.github/workflows/ci.yml` running on every push and PR: `uv sync`; `uv run pytest` (the suite needs no database); `make openapi-check`; a migration job that starts a `postgres:17` service container and runs `alembic upgrade head` from empty, proving the baseline plus chain stays applicable forever; and `ruff check` with a config added to `pyproject.toml` (defaults plus import sorting; initial findings fixed in a dedicated commit). Add `scripts/check_schema_drift.py`, which reflects `public` from a live database and diffs it against the app's table metadata; run it in CI against the migrated container and document in `docs/how-to/` how to run it against production. From M6 it also runs `lint-imports`. Add `lint` and `lint-imports` targets to the `Makefile`.

### M2 — Drop dead legacy structures

One migration, `<stamp>_drop_dead_legacy_tables.py`, dropping `aspnetusers`, `aspnetroles`, `aspnetuserroles`, `grupper_admin_kobling`, and `personal_fil` — each preceded by a guard query proving the audit's "unused" claim still holds. Before dropping the aspnet tables, export their rows to a private archive outside this public repository (historical admin list and 66 password hashes); record the location in the Decision Log. Remove the corresponding `Table` definitions and the `volunteer_documents`/`group_hierarchy` aliases. Rehearse on a Supabase development branch, run `make test`, apply to production. Deliberately small: it proves the branch-rehearse-apply loop before the big rename.

### M3 — Rename the database to English and fix column types

One migration, `<stamp>_rename_schema_to_english.py`, containing only `ALTER TABLE ... RENAME` statements per the rename map plus the type fixes: `events.updated_at` to `timestamptz NOT NULL DEFAULT now()` (backfill from `created_at`); a foreign key `groups.parent_group_id -> groups.id`; a foreign key `volunteer_application_group_members.dropped_by_user_account_id -> user_accounts.id` (`NOT VALID` + `VALIDATE` if orphans need cleanup); and renames of constraints/indexes whose names embed old table names (`uq_registrering_token`, the `ck_registrering_gruppe_medlem_*` checks, the pg_trgm and live-query indexes). Postgres rewrites stored references (views, policies, triggers) automatically on rename; re-check the M0 policy inventory on the branch afterward.

In the same commit, rewrite `app/db/table_defs/public.py` with native English names, delete the alias block, and sweep the repositories: Norwegian column access becomes English, and per-query `.label()` anglicization is removed. Templates and Pydantic models already speak English; `make test` and `make openapi-check` are the safety net. Update scripts that reference old names (grep `scripts/`).

Cutover, rehearsed end-to-end on a Supabase branch first: announce the window; `vercel deploy` the rename-aware code as a preview; `alembic upgrade head` against production; `vercel promote` immediately; smoke-check `/health`, login, volunteer list, `POST /api/v1/mobile-card/access-codes`, `/api/now-playing`. Renames are metadata-only (milliseconds); the window is deploy-promotion latency. Rollback inside the window is `alembic downgrade -1` (pure renames, exact inverse) plus the still-live previous deployment.

### M4 — Retire the legacy DigitalInternkort API and auth-bridge vestiges

Instrument first: a structured log event `legacy.digital_internkort.hit` (with user agent) in both handlers of `app/api/legacy/mobile_card.py`, deployed as early as M0 so the clock runs in parallel. After four consecutive weeks of zero non-synthetic hits: delete `app/api/legacy/`, its router registration, the two OpenAPI operations (via `make openapi`), and the legacy-shape tests. Retire the bridge vestiges at the same time: rename `LoginService.login_with_bridge` to `login`, drop `legacy_user_id` from `app/auth/models.py`, `app/auth/repository.py`, `app/domain/admin_accounts/service.py`, and ship `<stamp>_drop_auth_bridge_vestiges.py` dropping `auth_migration_events` and `user_accounts.legacy_user_id` (export `auth_migration_events` to the private archive first — it is the only record of how each admin account was migrated).

### M5 — Data-access overhaul: unit of work, typed rows, repository contracts

This milestone changes how every query runs without changing what any query returns.

First the unit of work. Add a request-scoped session dependency in `app/db/session.py` (`get_request_session`, yielding an `AsyncSession`, committing on success, rolling back on exception). `SqlAlchemyRepository` changes from holding a session *factory* to holding a *session*; its `fetch_*` helpers lose their `async with` blocks; `execute_in_transaction` and the per-method commit in `execute` are deleted. Repositories become cheap per-request objects constructed in `app/dependencies.py` with the request session; `app/runtime.py` keeps only genuinely process-lived things (settings, engine, caches, storage/email/Spotify adapters, session store). The seven call sites where services run transaction callbacks (`groups/service.py`, `courses/service.py`, `spotify/repository.py`, `mobile_card/april_state.py`) become plain sequential repository calls inside the request transaction. Background/script entry points (`scripts/`, smoke tests) get a small `session_scope()` async context manager so non-HTTP callers keep working.

Then typed rows. Each repository method's return type changes from `dict | list[dict]` to a concrete model: where a Pydantic response model already matches the row shape (true nearly everywhere after M3), the repository returns `Model.model_validate(row)` directly; internal read shapes that never leave the domain get `@dataclass(frozen=True, slots=True)` rows next to the repository. Delete `app/domain/volunteers/mappers.py` except the real derivations (full name, semester labels, gender labels), which move to model validators or small pure functions in the owning module. Replace every `Any` in `volunteer_applications/workflow.py`'s protocols with the real types. Remove the `repository or SomeRepository()` hidden defaults from all service constructors — dependencies are required and wired explicitly.

Finally, contracts and hygiene. Define a `Protocol` per repository (the workflow already shows the pattern) and add one contract test per module that runs the same scenario against the fake repository and the real one on the CI Postgres container, closing the fake-drift gap. Move media-URL minting and display-label formatting out of `groups/queries.py` (and any other read model) into the service/route layer — queries return data. Extract the hand-rolled keyset pagination (`after_last_name`/`after_first_name`/`after_volunteer_id`) into one shared helper in `app/db/`. Replace scattered `perf_counter` timing with a single SQLAlchemy `before/after_cursor_execute` event listener in `app/db/session.py` for uniform slow-query logging.

What this milestone deliberately does not do: adopt ORM-mapped classes or relationship loading. Core expressions are the right fit for this app's query shapes (JSON aggregates, keyset pagination, trigram search); the wins here are typing and lifecycle, not a different query API.

### M6 — Modular monolith with owned tables

Make ownership physical. Move each table's definition from `app/db/table_defs/public.py` into `app/domain/{owner}/tables.py` per the ownership map (all still bound to the one shared `MetaData` from `app/db/`, so Alembic and cross-module joins are unaffected). `app/db/table_defs/` retains only the shared metadata object and the `auth`/`storage` schema reflections. Fix the one ownership violation: migration `<stamp>_extract_mobile_card_access_codes.py` creates `mobile_card_access_codes` (`volunteer_id` PK/FK, `code_hash`, `created_at`), copies current values, and drops the two token columns from `volunteer_records`; `mobile_card/repository.py` now writes only its own tables.

Enforce the boundaries. Add `importlinter` config to `pyproject.toml` with three contract types: a layers contract (`web`/`api` may import `domain`; `domain` may import `db`/`infrastructure`/`shared`; nothing imports upward); an independence contract between domain modules' service/repository/workflow code; and explicit allowed read edges for read models — `{module}/queries.py` may import other modules' `tables.py` but never their services or repositories. Cross-module writes call the owning module's service: the one real case is application approval creating a volunteer, which becomes `VolunteerApplicationWorkflow` calling a `VolunteersService.create_from_application(...)` method instead of the applications repository inserting into `volunteer_records` directly. `lint-imports` joins CI (M1's workflow) and the Makefile.

Complete the module shape from ADR-001. Extract `app/domain/role_assignments/` (role-history queries, position management, semester-transfer preview/apply) out of `volunteers` — the ADR's listed follow-up. Split the two oversized modules along the read/write line: `volunteers` and `volunteer_applications` each get a `queries.py` holding list/search/detail read models (mirroring `groups/queries.py`), services keep writes. Wire through `app/dependencies.py` and `app/runtime.py`; move tests accordingly. Acceptance is structural: suite green, `lint-imports` green, no domain directory above ~1,200 lines, no single module above ~800.

### M7 — The volunteer application state machine

The most important business process becomes readable from one file, fulfilling ADR-001's stated intent literally.

Create `app/domain/volunteer_applications/state_machine.py`, pure and I/O-free: `ApplicationState(StrEnum)` (`PROSPECT`, `INVITED`, `SUBMITTED`, `PROMOTED`, `REJECTED`), `MembershipState(StrEnum)` (`ACTIVE`, `DROPPED`), `ApplicationAction(StrEnum)` (`SUBMIT_PROFILE`, `RESEND_INVITATION`, `MARK_TRIAL_SHIFT`, `APPROVE`, `REJECT`, `DELETE`, `DROP_MEMBER`), an explicit transition table `TRANSITIONS: dict[tuple[ApplicationState, ApplicationAction], ApplicationState]`, and a `transition(state, action, *, guards: TransitionContext) -> TransitionResult` function that returns the new state plus the named side effect to fire, or raises `IllegalTransition`. Guards encode the rules that depend on more than the state — the central one from the group-registration ADR: `APPROVE` on an application whose group membership is `ACTIVE` and whose group has other active members is illegal as a per-person action and legal only as the group-level action. The module docstring carries the state diagram; a test parametrizes the full state × action matrix so every cell is either asserted legal with its expected result or asserted to raise.

Re-wire the flow through it. `workflow.py` methods become: load typed record (M5) → `state_machine.transition(...)` → persist new state via repository → fire the named side effect from `side_effects.py` — all inside the request transaction (M5), which is what finally makes group approval atomic and all-or-nothing: one transaction promotes every active member or none. Replace the 14+ scattered status string literals in `repository.py` and `service.py` with the enums; the greppable invariant is that `"submitted"`-style literals appear in exactly one file. Implement the remaining ADR hardening: per-person approve hidden/blocked for active grouped applications (route + template + workflow guard), `Godkjenn alle` renamed to `Godkjenn gruppen`, the admin application list grouped by `group_id`, and tests for grouped approval, partial historical states, dropped members, and direct route access to blocked actions.

Constrain the database. Migration `<stamp>_application_state_constraints.py` adds `CHECK (status IN ('prospect','invited','submitted','promoted','rejected'))` on `volunteer_application_invites` (after an audit query confirms no other value exists in production — if one does, it is mapped and recorded in the Decision Log) and tightens transition-evidence columns where the audit allows (e.g. `promoted_at NOT NULL` when `status = 'promoted'` via a check constraint).

## Concrete Steps

All commands run from the repository root unless stated otherwise.

Capture the production schema (M0):

    pg_dump "$DATABASE_URL" --schema-only --schema=public --no-owner --no-privileges \
      > docs/reference/schema-snapshots/$(date +%Y%m%d)-pre-restructure.sql

Rehearse any migration on a Supabase development branch (M2, M3, M4, M6, M7): create the branch, point `DATABASE_URL` in `.env.branch` at the branch pooler, then:

    uv run alembic upgrade head
    uv run pytest -q
    uv run python scripts/check_schema_drift.py

Prove the baseline reproduces production on an empty database (M0, then CI forever):

    docker run -d --name pg-baseline -e POSTGRES_PASSWORD=x -p 55432:5432 postgres:17
    DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:55432/postgres uv run alembic upgrade head
    pg_dump postgresql://postgres:x@localhost:55432/postgres --schema-only --schema=public \
      --no-owner --no-privileges > /tmp/baseline-replay.sql

(Compare with `apgdiff` or a normalizing diff script; raw `diff` is too noisy. Acceptance is zero structural differences.)

Production cutover (M3), in order, inside the announced window:

    vercel deploy                       # build the rename-aware code as a preview
    uv run alembic upgrade head         # against production DATABASE_URL
    vercel promote <deployment-url>
    curl -fsS https://personal.kvarteret.no/health

Boundary and lint checks (M1 onward, M6 for imports):

    make lint            # ruff check .
    make lint-imports    # lint-imports (importlinter)
    make openapi && make openapi-check

State-machine invariant check (M7):

    grep -rn "'prospect'\|'invited'\|'submitted'\|'promoted'\|'rejected'" app/domain \
      --include='*.py' | grep -v state_machine.py
    # acceptance: no output

Full verification battery after each milestone:

    make test

## Validation and Acceptance

M0: the schema snapshot is committed, every production-only object has a Decision Log disposition, and `alembic upgrade head` on empty Postgres produces a schema structurally identical to the snapshot.

M1: a PR that breaks a test, stales `openapi.json`, fails ruff, or breaks the migration chain fails CI visibly on GitHub; `scripts/check_schema_drift.py` exits zero against the CI-migrated container.

M2: production no longer lists `aspnetusers`, `aspnetroles`, `aspnetuserroles`, `grupper_admin_kobling`, or `personal_fil`; the private archive export exists; `make test` passes with the definitions removed.

M3: production contains only English names from the rename map; login, volunteer detail, and `POST /api/v1/mobile-card/sessions` work; `make openapi-check` is clean; `grep -rn "fornavn\|etternavn\|kortnummer\|grupper\b" app/` matches nothing outside migrations.

M4: Vercel logs show four weeks of zero non-synthetic `legacy.digital_internkort.hit` events before removal; the DigitalInternkort routes 404 in production afterward; `openapi.json` no longer mentions them; `user_accounts` has no `legacy_user_id`.

M5: `grep -rn "session_factory()" app/domain app/auth` matches nothing (sessions enter only through the request dependency or `session_scope()`); `grep -rn "dict\[str, Any\]" app/domain/*/repository.py` matches nothing; `app/domain/volunteers/mappers.py` is deleted; a contract test per module passes against fake and real repositories in CI; one warm admin page that previously issued N connections issues 1 (assert via the new engine event listener's log output in a local timing run, recorded in `Artifacts and Notes`).

M6: every table definition lives in its owning module's `tables.py`; `make lint-imports` passes and CI fails on a deliberately introduced cross-module service import (verify once, then revert); `mobile_card_access_codes` exists and `volunteer_records` has no token columns; `app/domain/role_assignments/` exists; no domain directory exceeds ~1,200 lines (`find app/domain/* -name '*.py' | xargs wc -l`).

M7: the state × action matrix test covers every combination; the status-literal grep above returns no output; per-person approval of an active grouped member is rejected by the workflow and absent from the template; group approval promotes all active members in one transaction (test: induce a failure on the second member and assert the first is not promoted); the check constraint exists in production and an `UPDATE ... SET status='bogus'` is rejected.

## Idempotence and Recovery

Every migration is rehearsed on a Supabase development branch before production, and production is touched only with a verified PITR window or manual dump. M2 and M4 drops are preceded by archival exports; recovery is restoring the export. The M3 rename migration is symmetric (`downgrade()` renames back exactly); recovery inside the window is `alembic downgrade -1` plus the still-live previous deployment. The M6 token-table migration copies before dropping, so its downgrade re-creates the columns and copies back. The M7 check constraints are preceded by audit queries and are droppable independently. M5–M7 code changes are behavior-preserving refactors shipped behind the full suite, the contract tests, and (from M6) the import linter; each milestone ends with code and schema agreeing, so the plan can pause indefinitely at any milestone boundary.

## Artifacts and Notes

Current measured state (2026-06-10), the "before" picture:

    app python LOC: 18,388   tests LOC: 8,099   tests collected: 226
    domain module sizes: volunteer_applications 2,352  volunteers 2,318
                         groups 1,066  mobile_card 1,056
    volunteer_applications internals: repository.py 995, service.py 1,090,
                                      workflow.py 163, side_effects.py 104
    application status literals: 14+ sites across repository.py and service.py
    transaction callbacks in services: 7 sites (groups 5, courses 2)
    migrations: 24 revisions, no baseline
    dead tables in prod: aspnetusers (66 rows historically), aspnetroles,
                         aspnetuserroles, grupper_admin_kobling, personal_fil (88 rows)
    deprecated API: 2 DigitalInternkort operations in openapi.json
    CI: none (.github/workflows absent); Sonar config present

## Interfaces and Dependencies

Tooling additions: `ruff` and `import-linter` (dev dependencies), `apgdiff` or an equivalent schema-diff approach, GitHub Actions with a `postgres:17` service container. No new runtime dependencies — no ORM adoption, no workflow engine, no queue.

At the end of M3, `app/db/table_defs/public.py` defines `Table` objects whose SQL names equal their Python names, and `app/db/table_defs/__init__.py` contains imports only.

At the end of M5, in `app/db/session.py` and `app/db/repository.py`:

    async def get_request_session() -> AsyncIterator[AsyncSession]   # FastAPI dependency
    @asynccontextmanager
    async def session_scope(runtime: DatabaseRuntime) -> AsyncIterator[AsyncSession]

    class SqlAlchemyRepository:
        def __init__(self, session: AsyncSession) -> None: ...
        # fetch helpers typed as: async def fetch_all(self, stmt, into: type[T]) -> list[T]

At the end of M6, each owning module has `app/domain/{module}/tables.py`, `pyproject.toml` carries the importlinter contracts, and the volunteers module exposes:

    class VolunteersService:
        async def create_from_application(self, submission: ApplicationSubmission) -> int

At the end of M7, `app/domain/volunteer_applications/state_machine.py` exposes:

    class ApplicationState(StrEnum): PROSPECT; INVITED; SUBMITTED; PROMOTED; REJECTED
    class ApplicationAction(StrEnum): SUBMIT_PROFILE; RESEND_INVITATION; MARK_TRIAL_SHIFT;
                                      APPROVE; REJECT; DELETE; DROP_MEMBER
    TRANSITIONS: dict[tuple[ApplicationState, ApplicationAction], ApplicationState]
    def transition(state: ApplicationState, action: ApplicationAction,
                   *, context: TransitionContext) -> TransitionResult  # raises IllegalTransition

Revision note: Initial version authored from the 2026-06-10 research pass; no implementation started.

Revision note (revision 2, 2026-06-10): Folded in the data-access overhaul (request-scoped unit of work, typed rows, mapper deletion, repository contracts — new M5), the architecture decision and table-ownership enforcement (modular monolith with owned tables, import-linter, table definitions moved into modules, mobile-card token extraction — new M6), and the volunteer-application state machine including the group-registration ADR's unimplemented hardening list (new M7). CI moved from last to M1 because the new milestones are large refactors that need the pipeline first; former M1–M3 renumbered to M2–M4. Added research findings on session-per-call cost, transaction leakage into services, untyped rows, scattered status literals, and the mobile-card ownership violation. All decisions recorded in the Decision Log with alternatives considered.
