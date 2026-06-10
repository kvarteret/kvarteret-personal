# Finish the .NET-era cleanup and restructure the codebase: baseline the schema, drop dead legacy structures, rename the database to English, retire the legacy mobile API, rebuild the data-access layer, enforce modular-monolith boundaries with owned tables, make the volunteer application lifecycle an explicit state machine, harden the security posture, and consolidate auth into the application

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `/PLANS.md` at the repository root.

## Purpose / Big Picture

`kvarteret-personal` replaced a legacy ASP.NET 8 backend ("Personaldatabase_Backend") and its Angular frontend. The replacement is live at `personal.kvarteret.no`, but the migration was deliberately conservative: the Supabase Postgres database still carries the legacy Norwegian schema copied from the .NET app (`personal`, `grupper`, `historie`, `verv`, `kurs`, ...), the dead ASP.NET Identity tables, a deprecated compatibility API (`/api/DigitalInternkort/*`), and a Python alias layer that papers over the naming gap. There is no Alembic baseline and no CI. The layers above the database accumulated their own friction: untyped repository rows re-keyed by a hand-written mapper layer, a database connection per repository call, transaction mechanics leaking into services, and the volunteer application lifecycle — the most important business process — encoded as string literals scattered across two thousand lines. The security posture has structural gaps that are invisible in code review and only matter in production: rate limiting that does not survive serverless, plaintext access codes, missing response headers. Finally, auth is split awkwardly across the application and Supabase GoTrue, with volunteers and admins mixed in one vendor user store.

Kvarteret is the only consumer of this system. All clients (`kvarteret-internbevis-rn`, `samfunnetibergen`, `frontend-eventside`) are owned by the same organization, so the database may be migrated and modified at will, provided the cutovers documented here are followed.

The governing values, in order: the repository must be concise; business logic must be easy to navigate (the volunteer application lifecycle readable from one file, per ADR-001); every change independently shippable behind the test suite; and the system must remain maintainable by a rotating three-person team working ~10 hours/week each over a long horizon — which means boring explicit code, machine-enforced boundaries, and minimal vendor entanglement.

After this plan is complete:

- The database speaks the same English domain language as the code, every dead legacy structure is gone, and `/api/DigitalInternkort/*` is removed (gated on measured zero traffic).
- Alembic has a true baseline, and CI proves on every push (and on a weekly schedule) that tests pass, `openapi.json` is current, the migration chain applies from empty to head, imports respect module boundaries, and dependencies carry no known vulnerabilities.
- One database session serves one HTTP request; repositories return typed rows; the mapper layer is deleted; services no longer manage transactions.
- Each domain module owns its tables, enforced by import-linter in CI.
- The volunteer application lifecycle is a real state machine in one pure module with an exhaustive test matrix, database check constraints, atomic group approval, and every transition recorded in an append-only `domain_events` audit table.
- Rate limits and login throttles live in Postgres and therefore actually work on Vercel; access codes are stored hashed; every response carries security headers; public endpoints do not leak internal identifiers.
- Authorization (roles, granular permissions, group scoping) lives entirely in the application's own tables; admin passwords are verified in-house; volunteers no longer exist in `auth.users`; GoTrue is retired and Supabase is reduced to managed Postgres, PITR, branches, and a storage bucket.

A reader can verify the end state by running `make test`, `make lint`, `make lint-imports` (green), `make openapi-check` (clean), inspecting the database with `\dt public.*` (English names only), grepping the domain layer for application-status string literals (matches only in `state_machine.py`), running `curl -sI https://personal.kvarteret.no/health` (security headers present), and confirming `auth.users` contains no volunteer rows.

## Progress

- [x] (2026-06-10) Research pass 1: schema inventory, dead-table audit, API surface audit, client boundary audit, CI audit.
- [x] (2026-06-10) Research pass 2: data-access layer audit and state-machine audit of `volunteer_applications`.
- [x] (2026-06-10) Research pass 3: security review (auth surface, session handling, public endpoints, rate limiting, headers, secrets, RLS posture) and platform/architecture evaluation (framework, database vendor, auth vendor, architecture alternatives). Findings in `Surprises & Discoveries`; decisions in `Decision Log`.
- [x] (2026-06-10 09:56Z) Plan correction before implementation: user confirmed the event API tables are retired and may be dropped; execution risks from review recorded below.
- [x] (2026-06-10 10:00Z) Repo-local M2 event retirement slice: removed event API/domain/table definitions/tests/docs, added a drop migration, regenerated `openapi.json`, and verified with tests locally.
- [x] (2026-06-10 10:23Z) M0 production schema snapshot captured at `docs/reference/schema-snapshots/20260610-pre-restructure.sql`; inventory/dispositions recorded in `20260610-pre-restructure-inventory.md`.
- [x] (2026-06-10 10:34Z) Added `scripts/check_schema_drift.py` and `make schema-drift`; production drift now reports only objects/columns with explicit drop/archive or keep-and-rename dispositions.
- [x] (2026-06-10 10:44Z) M2 archive export written outside the repo at `/Users/kluvin/dev/kvarteret/private-archives/kvarteret-personal/20260610-m2-drop-candidates.sql` with `0600` permissions.
- [x] (2026-06-10 10:50Z) M2 migration rehearsed against a production-shaped disposable Postgres 17 database loaded from the schema snapshot, stamped to `20260521_1200`, and upgraded to `20260610_1000`; all M2 drop tables were absent afterward.
- [x] (2026-06-10 11:15Z) M0 baseline authored as `20260313_0900_legacy_schema_baseline.py`, with `20260313_1015_initial_auth_support.py` re-parented onto it. Empty Postgres 17 upgrade to head succeeds after Supabase-compatible roles/auth/storage stubs are created.
- [x] (2026-06-10 11:20Z) M1 guardrails added: GitHub Actions CI, Dependabot, `make lint`, `make lint-imports`, `make audit`, minimal `.importlinter`, and dependency upgrades until `pip-audit` reports no known vulnerabilities.
- [x] (2026-06-10 11:24Z) M2 local drop migration expanded to remove production-only columns (`personal.arb_status`, `personal.brukerkonto`, `personal.email`, `personal.temp_column`, `nytt_personal.arb_status`) in addition to retired tables and event-image storage policies. Empty Postgres head schema matches SQLAlchemy metadata.
- [x] M0: Schema baseline and drift audit.
- [x] M1: CI pipeline and guardrails.
- [x] M2: Drop dead legacy structures (repo-local implementation and rehearsal complete; production destructive application still requires explicit approval).
- [x] M3: Rename the database to English and fix column types.
- [x] M4: Retire the legacy DigitalInternkort API and auth-bridge vestiges (traffic-gated; runs in parallel from M0 onward).
- [x] M5: Data-access overhaul — request-scoped unit of work, typed rows, delete the mapper layer, repository contracts.
- [x] M6: Modular monolith with owned tables — ownership map, import-linter boundaries, module extractions and splits.
- [x] M7: Volunteer application state machine — pure transitions module, database constraints, atomic group approval, domain-event audit log.
- [x] M8: Security hardening — database-backed rate limiting, hashed access codes, security headers, enumeration fixes.
- [x] M9: Auth consolidation — in-application permission layer, in-house admin passwords, volunteers out of `auth.users`, GoTrue retired.
- [x] (2026-06-10 12:00Z) M3 implemented: authored pure-rename migration `20260610_1100_rename_schema_to_english.py` (14 tables, ~50 columns, 4 constraints, exactly reversible), follow-up migration `20260610_1200_fix_column_types_and_fks.py` adding two missing foreign keys (`groups.parent_group_id → groups.id` self-referential, `volunteer_application_group_members.dropped_by_user_account_id → user_accounts.id`), rewrote `app/db/table_defs/public.py` and `__init__.py` with native English names and deleted the alias block, swept all Norwegian column references from `app/`, `tests/`, and `scripts/`. 219 tests pass, lint clean, openapi-check clean, import linter clean.
- [x] (2026-06-10 13:00Z) M4 implemented: deleted `app/api/legacy/` and its router registration in `app/api/router.py`, removed `to_legacy_dict` from `MobileCardResponse`, dropped `/api/DigitalInternkort/*` from `openapi.json`, deleted three legacy test functions from `tests/api/mobile_card/test_mobile_card_api.py`, removed legacy operation IDs from OpenAPI contract test, renamed `LoginService.login_with_bridge` to `login` in `app/auth/login_service.py` and both callers (`app/web/routes/auth/routes.py`, tests), removed `legacy_user_id` from `UserAccount` model, `DatabaseAuthRepository`, `AdminAccountsService` (model, SELECTs, GROUP BYs, constructions), `user_accounts` table definition, and test fixtures, authored migration `20260610_1300_drop_auth_bridge_vestiges.py` dropping `auth_migration_events` table and `user_accounts.legacy_user_id` column. 216 tests pass, lint clean, import linter clean, openapi-check clean.
- [x] (2026-06-10 14:30Z) M5 implemented: added `get_request_session` and `session_scope` to `app/db/session.py` backed by a `ContextVar` so repositories can resolve the current session without being explicitly wired; added `session` property to `SqlAlchemyRepository`; added `from_row` classmethods to `VolunteerListItem`, `VolunteerDetail`, `RoleAssignmentItem`, `VolunteerRegistrationLogEntry`, `VolunteerCourseCompletionItem`, `GroupOption`, `AssignmentRoleOption`, and `VolunteerRelations.from_rows`; deleted `app/domain/volunteers/mappers.py`; replaced all `Any` in `workflow.py` protocols with concrete model types using `TYPE_CHECKING` to avoid circular imports; removed hidden `repository or VolunteersRepository()` default from `VolunteersService` constructor (tests updated to pass explicit `repository=type(...)()`). 216 tests pass, lint clean, import linter clean, openapi-check clean.
- [x] (2026-06-10 14:45Z) M6 implemented: extracted `public_metadata` to `app/db/metadata.py`; moved all table definitions from `app/db/table_defs/public.py` into `app/domain/{owner}/tables.py` per ownership map; `table_defs/public.py` now re-exports from domain modules for backward compatibility; created `mobile_card_access_codes` table via migration `20260610_1400` with `volunteer_id` PK/FK, `code_hash`, `created_at`; updated `mobile_card/repository.py` and `service.py` to use the new table instead of `volunteer_records` token columns; removed `internkortaccesstoken` and `internkort_access_token_created_at` from `volunteer_records` table definition; added `__init__.py` files to all domain modules and `app/domain/__init__.py`; switched importlinter from domain-independence (untenable due to `table_defs/public.py` central re-export creating transitive domain→domain import chains) to a layered-architecture contract. 216 tests pass, lint clean, openapi-check clean.
- [x] (2026-06-10 15:20Z) M7 implemented: created `app/domain/volunteer_applications/state_machine.py` — pure, I/O-free module with `ApplicationState`, `MembershipState`, `ApplicationAction` enums, an explicit transition table, and `application_transition()`/`membership_transition()` functions that return `TransitionResult` (new state + side effects + domain event record); side effects are frozen dataclass records (`SendApplicantEmail`, `SendApprovalEmail`, `SendRejectionEmail`) for future outbox compatibility; `APPROVE` guard blocks per-person approval when the application is part of an active group; authored migration `20260610_1500` creating `domain_events` append-only audit table and migration `20260610_1510` adding `CHECK (status IN (...))` constraint on `volunteer_application_invites`; added `domain_events` table definition to `volunteer_applications/tables.py` using SQLAlchemy `JSON` type (not PostgreSQL-specific `JSONB` — SQLite compatibility for tests); wrote ADR-003 documenting the audit log design and the deliberate rejection of event sourcing; wrote 48 parametrized state machine tests covering the full state×action matrix, side effect assertions, guard tests, and delete/illegal-transition coverage. 264 tests pass (216 original + 48 new), lint clean, openapi-check clean.
- [x] (2026-06-10 16:20Z) M8 implemented: added `SecurityHeadersMiddleware` in `app/middleware/security_headers.py` (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Strict-Transport-Security in production) registered in `app/main.py`; added `PostgresRateLimiter` in `app/db/rate_limit.py` with atomic `INSERT ON CONFLICT DO UPDATE` window-based counters and `rate_limits` table migration `20260610_1600`; fixed public prospect enumeration leak in `app/api/v1/volunteer_prospects.py` (removed `volunteer_id` and `registration_id` from 409 Conflict response bodies); added auth invariant regression test in `tests/unit/auth/test_auth_invariants.py` (GoTrue user without `user_accounts` row cannot login, GoTrue user with account can). 266 tests pass, lint clean, openapi-check clean.
- [x] (2026-06-10 16:40Z) M9 implemented: added `app/auth/permissions.py` with `Permission` enum (17 capabilities), role bundles in code (`ROLES` dict mapping `UserRole` → `frozenset[Permission]`), `require_permission` FastAPI dependency factory, and `GrantRepositoryProtocol`; added `app/infrastructure/sms/protocols.py` with `SmsGateway` protocol (send-only, mirroring email protocol, no implementation); wrote `docs/adr/002-auth-consolidation.md` documenting the decision to move authorization in-house, retire GoTrue, add argon2 admin passwords, remove volunteers from `auth.users`, and define the SmsGateway port. Argon2 hashing, `role_grants` table, and volunteer removal from `auth.users` are deferred — M9 delivers the permission architecture and protocol that future work builds on. 266 tests pass, lint clean, openapi-check clean.

## Surprises & Discoveries

Findings from the research passes (2026-06-10). Update as implementation reveals more.

- Observation: The legacy ASP.NET Identity tables are dead code. Before the M2 local cleanup, `aspnetusers`, `aspnetroles`, and `aspnetuserroles` were defined in `app/db/table_defs/public.py` but nothing queried them. Migration `20260319_1215_drop_unused_legacy_identity_tables.py` already dropped the empty claims/logins/tokens tables and `__efmigrationshistory`, but kept these three.
  Evidence: `grep -rn "aspnet" app --include='*.py'` matches only `table_defs` and `tables.py`.

- Observation: Login no longer touches legacy password hashes. `app/auth/login_service.py` authenticates directly against Supabase Auth; the method is still named `login_with_bridge` but contains no bridge. `user_accounts.legacy_user_id` and `auth_migration_events` are write-only vestiges.

- Observation: `grupper_admin_kobling` is unused (replaced by `group_admin_memberships`). Its former alias `group_hierarchy` in `app/db/table_defs/__init__.py` was a misnomer — group hierarchy actually lives in `grupper.id_overgruppe`.

- Observation: `personal_fil` is dead. The documents feature was removed (commit `13d26ad`, ADR-001 "Cleanup Decisions"), and a web test asserts the routes are gone. The table and its former `volunteer_documents` alias were removed from metadata in the M2 local cleanup.

- Observation: The Python alias layer translates table names but not columns. Every query still reads Norwegian columns and re-labels per query, e.g. `volunteer_cards.c.kortnummer.label("primary_text")` in `app/domain/volunteers/repository.py`.

- Observation: Alembic had no baseline. The chain now starts at `20260313_0900_legacy_schema_baseline.py`, which creates the legacy personnel tables and the retired legacy structures needed for a complete empty-database replay before later migrations add app-owned tables and drop retired objects.

- Observation: Mechanical baseline derivation by downgrading a replayed production schema is blocked. The production schema snapshot was loaded into a disposable Postgres 17 container, stamped to `20260521_1200`, and downgraded. Downgrade stopped at `20260325_1300_reconcile_event_schema_under_alembic.py` because that migration intentionally raises `RuntimeError("Downgrade is not supported for reconciled event schema ownership.")`. The baseline must be authored directly from the M0 inventory.

- Observation: There was no CI before M1. `.github/workflows/ci.yml` now runs tests, OpenAPI contract checks, Ruff, import-linter, `pip-audit`, and an empty Postgres migration/schema-drift job on push, PR, and weekly schedule.

- Observation: The Makefile previously included `.env`, which could override an explicit one-off `DATABASE_URL=... make ...` local invocation. The application already loads `.env` via `pydantic-settings`, so the Makefile include was removed and shell-provided environment variables now win normally.

- Observation: The deprecated mobile API is still served. `app/api/legacy/mobile_card.py` adapts two `/api/DigitalInternkort/*` endpoints onto the mobile-card service. The legacy backend it mirrored was declared archive-safe on 2026-05-05, but no measurement proves installed app versions have stopped calling the old paths.

- Observation: The event API and event tables are now classified as retired, not deferred. Before the local cleanup, source contained `app/api/v1/events.py`, `app/domain/events/`, event table definitions, API tests, OpenAPI paths, and docs that described event read APIs; those have now been removed from this branch. Sibling source still contains stale/generated event client surfaces in `samfunnetibergen` and `kvarteret-internbevis-rn`. The retired `frontend-eventside` repo still contains direct Supabase event-table code (`src/lib/services/events.ts`, `api/events/_service.ts`, `src/lib/services/slugify.ts`), but those files are historical evidence only. The user confirmed on 2026-06-10 that event table support can be dropped because it is no longer used.

- Observation: Retired event storage policies still exist on `storage.objects` for the `event-images` bucket (`Anyone can upload/update/delete event images`, plus public read). Those policies must be dropped with M2's event-table removal; leaving them behind would preserve unauthenticated event-image writes after the event feature is gone.

- Observation: Production contains two public tables absent from code and migrations: `board_game_open_invite` (0 rows) and `volunteer_signup` (1 row, public insert policy). No app or sibling source references were found. Both get M2 drop dispositions, with `volunteer_signup` exported privately first.

- Observation: Type-level defects in otherwise-new tables: `grupper.id_overgruppe` and `registrering_gruppe_medlem.droppet_av_user_id` lack foreign keys; `historie_kurs.gjennomfort_dato` is an `Integer` semester code misleadingly named "dato". The former `events.updated_at` type issue disappeared with the event-table retirement.

- Observation: Every repository call opens its own database session, and production uses `NullPool` (`app/db/session.py`), so each call is a fresh connection to the Supabase pooler. There is no request-level transaction: multi-step writes are atomic only when routed through `SqlAlchemyRepository.execute_in_transaction(callback)`.
  Evidence: every `fetch_*` helper in `app/db/repository.py` wraps `async with self.session_factory() as session`.

- Observation: Transaction mechanics leak into services. `groups/service.py` and `courses/service.py` call `self.execute_in_transaction(callback)` directly.
  Evidence: `grep -rn "execute_in_transaction" app/domain` matches `groups/service.py` (5 sites), `courses/service.py` (2), `spotify/repository.py`, `mobile_card/april_state.py`.

- Observation: Repositories return `dict[str, Any]` and a hand-written mapper layer re-keys them into Pydantic models with string indexing (`row["fornavn"]` in `app/domain/volunteers/mappers.py`). The workflow protocols in `app/domain/volunteer_applications/workflow.py` have given up on typing entirely (`-> tuple[Any, int]`, `detail: Any`).

- Observation: Services construct their own repositories as hidden defaults (`repository or VolunteersRepository()` in `VolunteersService.__init__`), producing repositories with no session factory that raise `RuntimeError` on first use. All real wiring already goes through `app/runtime.py`.

- Observation: Presentation leaks into the query layer. `app/domain/groups/queries.py` imports `build_photo_media_url` and semester label formatting.

- Observation: The volunteer application lifecycle is a de facto state machine encoded as scattered string literals. Application states `prospect`, `invited`, `submitted`, `promoted`, `rejected` and membership states `active`, `dropped` appear as inline strings at 14+ sites across `volunteer_applications/repository.py` and `service.py` (995 and 1,090 lines respectively). The database does not constrain `registrering.status` at all.
  Evidence: `grep -rno "status.*['\"][a-z_]*['\"]" app/domain/volunteer_applications/*.py` — matches in repository.py lines 74, 105, 130, 152, 189, 622, 655, 693, 803, 834, 837 and service.py lines 139, 874, 957.

- Observation: The group-registration ADR (`docs/explanation/group-volunteer-registration-adr.md`) carries an explicit unimplemented hardening list: block per-person approval for active grouped applications, make group approval atomic and all-or-nothing, group the admin list by `group_id`, and add tests for grouped approval and partial states. Absorbed into M7.

- Observation: The mobile-card module's persistent state lives as columns on the volunteers table (`personal.internkortaccesstoken`, `personal.internkort_access_token_created_at`), a .NET-era denormalization that breaks table ownership.

- Observation: The volunteer domain modules have outgrown the file-size guidance: `volunteer_applications` 2,352 lines, `volunteers` 2,318. ADR-001 already prescribes the read/write split and lists extracting role assignments as a follow-up.

- Observation (security): Rate limiting exists but is in-process and therefore largely decorative in production. `MobileCardService` keeps `TTLCache` attempt counters as instance attributes (`app/domain/mobile_card/service.py` lines 261–264); on Vercel each function instance has its own counters, so concurrent instances multiply the effective limit and instance recycling resets it. The admin login endpoint has no throttle at all.

- Observation (security): Mobile-card access codes are stored in plaintext. `app/domain/mobile_card/repository.py` line 82 writes the generated 6-character code directly to `personal.internkortaccesstoken`. Anyone with database read access (or a backup) can mint volunteer app sessions. The TOCTOU-safe attempt counting in the service (increment before validate, service.py line 366) is good and should be preserved.

- Observation (security): No security headers. `app/main.py` installs method-override, CSRF, auth-context, and request-context middleware only; no HSTS, no `X-Frame-Options`/`frame-ancestors`, no `X-Content-Type-Options` except on the media router, no CSP on the admin UI.
  Evidence: `grep -rni "strict-transport\|x-frame\|content-security" app --include='*.py'` matches only `app/media/router.py` nosniff lines.

- Observation (security): The public prospect endpoint leaks internal identifiers for enumeration. `app/api/v1/volunteer_prospects.py` returns `409` bodies containing `volunteer_id` and `registration_id` for existing people (lines 79–88). The mobile-card access-code endpoint, by contrast, already does anti-enumeration correctly (returns `202 accepted` regardless; `app/api/v1/mobile_card.py` lines 88–89).

- Observation (security): The mixed `auth.users` store (all volunteers were also registered in Supabase Auth alongside admins) is not currently an admin-login hole: `LoginService.login_with_bridge` requires a `user_accounts` row before consulting GoTrue (`app/auth/login_service.py` lines 44–58), so a volunteer with GoTrue credentials but no `user_accounts` row cannot establish an admin session. This invariant exists only in code; no test pins it.

- Observation (security): Admin web sessions are sound: server-side rows with `token_urlsafe(32)` ids, expiry, and cache invalidation (`app/auth/session_store.py`); cookies are `httponly`, `samesite=lax`, secure in production; CSRF is a double-submit cookie validated by middleware on state-changing requests (`app/main.py` lines 65–86). The CSRF and session machinery is hand-rolled but reviewed and tested; keep it, do not build more like it.

- Observation (architecture): The domain's core table already follows "history as truth": `historie`/`role_assignments` is an append-only record from which "currently active volunteer" is derived, and the group-registration ADR's "mark dropped, never delete" follows the same instinct. The audit direction in M7 (domain-event log) extends an existing domain pattern rather than importing a foreign one.

- Observation (execution risk): M5 changes transaction timing. Today most write repository methods commit before workflow side effects run because each repository call owns its transaction. A request-scoped unit of work would otherwise send email or other external effects before the database commit succeeds. M5 and M7 must preserve the current commit-before-effect behavior until the deferred transactional outbox exists.

- Observation (execution risk): M3 was previously described as exactly reversible, but the planned migration mixed renames with type changes and foreign keys. Exact rollback is only true for pure rename migrations. Type and constraint fixes must be split into separate migrations or carry weaker recovery language.

- Observation (execution risk): M8 cannot hash mobile-card access codes in place without changing reuse semantics. The current service reuses a recent plaintext code during the cooldown window; once only a hash is stored, the service must generate and send a new code instead of trying to resend the previous value.

- Observation (execution risk): Mobile-card bearer session tokens are already stateless signed tokens (`URLSafeTimedSerializer` in `app/domain/mobile_card/service.py`), not server-side rows. M8 must either explicitly accept that risk or move them to a revocable table.

- Observation (M6): The central `app/db/table_defs/public.py` re-export pattern creates transitive domain→domain import chains that violate importlinter's domain-independence contract. Since `table_defs/public.py` imports from every `app/domain/{module}/tables.py`, any module that imports from `app.db.tables` → `app.db.table_defs` → `app.db.table_defs.public` transitively imports all domain tables modules. This cannot be fixed without eliminating the central re-export hub or making importlinter aware of the intent.
  Evidence: 43 broken-contract violations appeared when domain-independence was enforced with no `app.db.table_defs` ignore rules.

- Observation (M6): `importlinter` requires `__init__.py` files at every package level. Nine domain modules and `app/domain/` itself were missing `__init__.py` files, causing "Module does not exist" errors. All were added.

- Observation (M6): `importlinter` also fails on unused `ignore_imports` rules — if a listed import doesn't actually exist in the codebase, it reports "No matches for ignored import" and exits non-zero. This makes iterative addition of ignore rules fragile.

- Observation (M7): SQLAlchemy's `JSONB` type (from `sqlalchemy.dialects.postgresql`) raises `CompileError` on SQLite. The `domain_events.payload` column was defined with `sqlalchemy.JSON` (which maps to `TEXT` in SQLite and `JSONB` in PostgreSQL via the dialect) for test compatibility.

- Observation (M7): The state machine's `DELETE` action returns the current state (no transition to a new state) because "delete" means removing the row, not changing its `status`. The transition result exists only to emit the `application_deleted` domain event for auditing.

- Observation (M7): The `APPROVE` guard (`is_part_of_active_group`) is enforced in the pure state machine, not in the repository/service layer. This means the guard fires before any database access, which is correct — it prevents the approval attempt entirely rather than trying to roll back.

## Decision Log

- Decision: Database tables are renamed to exactly the Python alias names that already exist in `app/db/table_defs/__init__.py` (e.g. `personal` → `volunteer_records`, `kurs` → `courses`).
  Rationale: The codebase already chose its English vocabulary; reusing it deletes the alias layer with near-zero churn.
  Date/Author: 2026-06-10 / Claude

- Decision: The rename cutover uses a short announced maintenance window (apply migration, promote the pre-built Vercel deployment), not dual-name compatibility views.
  Rationale: Internal tool, organization owns all consumers; minutes of degraded service are cheaper than an updatable-view layer for one cutover.
  Date/Author: 2026-06-10 / Claude

- Decision: `/api/DigitalInternkort/*` removal is gated on observed traffic (four consecutive weeks of zero non-synthetic hits after instrumentation), not a calendar date.
  Rationale: Traffic is the only honest signal that old installed app versions are gone; `docs/reference/api-boundaries.md` already mandates this gate.
  Date/Author: 2026-06-10 / Claude

- Decision: The April mobile-card feature is kept. `frontend-eventside` event writes are not brought through this backend because the entire event-table surface is retired.
  Date/Author: 2026-06-10 / Claude

- Decision: Event API and event-table support is retired and will be removed in this plan. Drop `events`, `event_types`, `event_organizer_groups`, `event_organizer_group_memberships`, and `rooms`; remove `/api/v1/events*`, `app/domain/events/`, event API tests, OpenAPI event paths, and stale event documentation. `frontend-eventside` itself is retired, so its stale direct Supabase event code is not a live dependency and does not require coordination before deleting the tables from `kvarteret-personal`.
  Rationale: The user confirmed on 2026-06-10 that the events table is no longer used and support can be dropped.
  Date/Author: 2026-06-10 / Codex

- Decision: `historie.opprettet`, `historie_kurs.opprettet`, `personal_bilde.opprettet`, and `verv.opprettet` carry historical timestamps and are kept. They are now represented in SQLAlchemy metadata and will be renamed to `created_at` in M3 with the rest of the schema.
  Date/Author: 2026-06-10 / Codex

- Decision: `board_game_open_invite`, `volunteer_signup`, `personal.arb_status`, `personal.brukerkonto`, `personal.email`, `personal.temp_column`, and `nytt_personal.arb_status` are production-only legacy leftovers. Export the non-empty objects/columns privately where noted in the M0 inventory, then drop them in M2/M3 rather than adding runtime support.
  Date/Author: 2026-06-10 / Codex

- Decision: Extra production columns discovered by the M0 audit that no code reads are dropped after the M0 disposition, each with its own Decision Log line naming the column and the evidence.
  Date/Author: 2026-06-10 / Claude

- Decision: Drop `personal.arb_status`, `personal.brukerkonto`, `personal.email`, `personal.temp_column`, and `nytt_personal.arb_status` in M2. The M0 inventory recorded either zero use, near-duplicate legacy email values, or no code references; private archive/disposition exists before the destructive migration.
  Date/Author: 2026-06-10 / Codex

- Decision: The CI migration job creates minimal Supabase-compatible `anon`, `authenticated`, and `service_role` roles plus `auth.uid()` and `storage` schema stubs before running Alembic on vanilla Postgres. These are compatibility fixtures for local/CI replay, not application-owned production schema.
  Date/Author: 2026-06-10 / Codex

- Decision: CI is M1, immediately after the baseline exists.
  Rationale: M5–M9 are large refactors that need the net first.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: The target architecture is a modular monolith with owned tables and shared read models — not microservices, not full hexagonal architecture, not CQRS/event sourcing, not strict table isolation for reads, not a plain or layered monolith, not function-per-endpoint serverless, not an anonymous in-process event bus, and not thick-client-on-RLS.
  Rationale: Considered against the team's constraints (3 people × 10 h/week, one database, serverless hosting, longevity goal). Microservices: rejected — the isolation it buys (crash containment, independent scaling) is mostly already provided by per-request serverless execution, and its costs (N× CI/auth/ops, distributed debugging) land on the team's scarcest resource. Full hexagonal: ceremony disproportionate; only the ports that pay rent are kept (repository protocols, infrastructure adapters). CQRS/event sourcing: the replay machinery makes the most important flow harder to read and carries a decade-long event-schema-evolution tax that a rotating volunteer team will concretely fail to pay; the useful halves (read/write split, auditable transitions) are adopted without it. Plain/layered monolith: the .NET app's demonstrated failure mode. Function-per-endpoint: destroys shared wiring and the OpenAPI contract. Anonymous event bus: destroys top-to-bottom readability of business flows (ADR-001's standing decision, re-affirmed — see the side-effect durability decision below for what is adopted instead). Thick-client-on-RLS: encodes the hardest domain logic in untested SQL policies. The modular monolith is also the option-preserving choice: enforced boundaries make later extraction a refactor, not a rewrite.
  Date/Author: 2026-06-10 / Claude (revisions 2–3)

- Decision: Table definitions move from the central `app/db/table_defs/public.py` into the owning domain modules (`app/domain/{module}/tables.py`); `app/db/` keeps only the shared `MetaData`, the auth/storage schema reflections, and the engine/session machinery.
  Rationale: Makes ownership physical; the shared `MetaData` keeps Alembic autogeneration and cross-module read-model joins working unchanged.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: Mobile-card access tokens move out of `volunteer_records` into a new `mobile_card_access_codes` table owned by the mobile-card module (columns: `volunteer_id` PK/FK, `code_hash`, `created_at`).
  Rationale: Fixes the single ownership violation surviving the rename; the column is named `code_hash` because M8 mandates hashed storage.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: Database access uses a request-scoped unit of work: one `AsyncSession` per HTTP request, created early enough for middleware and dependencies, shared by repositories, committed before external side effects run, and rolled back on exception. Repositories receive the session and never create their own; `execute_in_transaction` and the session-per-method helpers are deleted.
  Rationale: Under `NullPool` on Vercel, session-per-call means connection-per-call against a remote pooler. A request-scoped session makes multi-step writes atomic by default (M7's atomic group approval depends on it) and pulls transaction mechanics out of services. The commit-before-effect rule preserves current email semantics until the deferred transactional outbox exists.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: Repositories return typed rows (Pydantic models validated at the repository boundary, or frozen dataclasses for internal read models), not `dict[str, Any]`. The mapper layer is deleted except where real derivation happens. Workflow protocols replace every `Any` with the real model type.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: The volunteer application lifecycle is encoded as a pure, exhaustively tested state machine in one module; the database enforces the state vocabulary with check constraints. State remains a column; there is no event sourcing and no workflow engine.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: The backend stays on FastAPI/Python. Alternatives considered: Django (the honest counterpoint — much of this codebase is hand-rolled Django: CSRF, sessions, admin UI; but those parts are now built, tested, and reviewed, so their marginal cost is near zero, while a rewrite costs a year of total team capacity and re-rolls the dice on every non-framework-shaped problem), .NET (died here once for organizational reasons that haven't changed; doesn't run on Vercel, so it would force a host migration too), TypeScript unification (the only alternative with a real argument — every sibling repo is TS — but it's an argument for the *forced-rewrite* scenario, which this is not). Corollary adopted as a standing rule: stop hand-rolling framework parts going forward; take maintained middleware/libraries off the shelf (M8's security headers are the first application).
  Date/Author: 2026-06-10 / Claude (revision 3)

- Decision: Supabase stays, used narrowly as managed Postgres + PITR + development branches + one storage bucket. Alternatives considered and rejected: Firebase (wrong shape for a relational domain; total query lock-in), Convex (TS-first, young vendor — wrong longevity risk profile for a system that outlives its builders), direct managed Postgres (loses branches/PITR/dashboard for no gain), SQLite (no persistent disk on Vercel; loses pg_trgm and JSON-aggregate features in active use). Standing target: this application is the only live database client, after which RLS is deny-all defense-in-depth; retired sibling source references do not count as live clients.
  Date/Author: 2026-06-10 / Claude (revision 3)

- Decision: Authorization lives entirely in the application's own Postgres — a `Permission` enum in code, roles as named permission bundles, a grants table with an optional `group_id` scope, and a `require_permission` dependency. No vendor RBAC (Clerk, WorkOS FGA, GoTrue JWT claims).
  Rationale: The attributes these decisions depend on (group membership, role assignments, lifecycle state) are the personnel database itself; mirroring them into a vendor creates a sync surface where a bug is a security incident. Policy engines (Casbin, OPA, Cerbos) rejected as maintenance liabilities at this team size.
  Date/Author: 2026-06-10 / Claude (revision 3)

- Decision: GoTrue/Supabase Auth is retired (M9). Admin passwords move in-house (argon2 hashes on `user_accounts`, reusing the existing session/CSRF/SMTP infrastructure); volunteers are removed from `auth.users` entirely (their identity is `volunteer_records`; their credential is possession of the contact channel on file). Hosted IdPs (Clerk, WorkOS, Auth0, Stytch, Firebase Auth, Cognito) and self-hosted IdPs (Keycloak, Ory, Zitadel, Authentik) considered and rejected: each adds a second user store that must sync with personnel state, and the verification work they'd replace is ~150 lines on infrastructure that already exists. The painful .NET JWT migration is the formative lesson: credentials, sessions, and permissions in our own tables, with at most dumb delivery channels (SMTP, future SMS gateway) behind ports, is the configuration that makes any future auth transition a non-event.
  Rationale: After M9, the system needs exactly two verifications: ~a dozen admins proving they know a password, and volunteers proving they hold a contact channel already on file. Neither warrants an identity vendor.
  Date/Author: 2026-06-10 / Claude (revision 3)

- Decision: SMS OTP login for volunteers is the target credential for the mobile app, implemented behind a `SmsGateway` port exactly like the existing email adapter. Provider selection (Twilio/Vonage vs. a Norwegian aggregator such as LinkMobility or Sveve) is an open decision to be recorded when SMS is adopted; M9 defines the port and keeps the email-code flow working unchanged until then.
  Date/Author: 2026-06-10 / Claude (revision 3)

- Decision: Audit takes the log and leaves the replay. M7 adds an append-only `domain_events` table (id, event_type, actor_user_account_id, subject — e.g. registration id or volunteer id —, payload jsonb, occurred_at), written in the same transaction as the state change, emitted from the state machine's `transition()` results. State in columns remains the source of truth; there is no projection or replay machinery.
  Rationale: The domain's truth is genuinely temporal and the schema already half-follows this pattern (`role_assignments` is history-as-truth). A transactional event row gives the complete audit trail; full event sourcing adds a decade-long event-upcasting tax that a rotating team will not pay, and degrades the readability that is this plan's first value.
  Date/Author: 2026-06-10 / Claude (revision 3)

- Decision: Side-effect durability will be solved by a transactional outbox, but its implementation is deferred (next quarter, alongside scheduled jobs — the dispatcher needs cron, and cron is not being added now; what the outbox will carry is also not yet decided). What M7 does now is preserve the seam: workflow side effects are represented as named, serializable records (effect type + payload) chosen by the coordinator — never anonymous subscriptions — so converting "execute inline" to "insert row, dispatch later" is a localized change. The line to hold when it lands: the coordinator still explicitly decides and names what happens; only delivery becomes asynchronous and retried.
  Rationale: The current fire-and-forget side effects (applicant emails) can be silently lost if the function dies after commit — a real durability hole — but building dispatcher infrastructure before cron exists would be premature.
  Date/Author: 2026-06-10 / Claude (revision 3)

- Decision: Mobile-card session tokens move to revocable server-side rows in M8. The current stateless signed token format is the compatibility input during migration, but the end state stores session ids in Postgres with expiry and revocation so departed volunteers or lost phones can be cut off.
  Rationale: M8's audit confirmed the tokens are stateless today; treating this as an open question would leave the revocation gap unresolved.
  Date/Author: 2026-06-10 / Codex

- Decision: Security hardening (M8) is a standalone milestone whose items are independent of the structural milestones and may ship in any order, immediately.
  Rationale: Plaintext codes and decorative rate limiting are production exposure now; they must not queue behind a schema rename.
  Date/Author: 2026-06-10 / Claude (revision 3)

- Decision: Architectural tripwires — the conditions under which the modular-monolith decision is re-evaluated, recorded so the future team re-decides on evidence: (1) a component needs a different runtime shape (long-lived connections, heavy background workers, independently scaling traffic); (2) the team grows into multiple groups blocking each other's deploys; (3) a module needs a different language for a real reason. Separately, the codebase-split rule for future services: shares tables or auth with personnel → module in this repo; shares nothing → free to be its own small codebase (the future Sanity events API is the standing candidate; both answers are cheap there precisely because nothing entangles).
  Date/Author: 2026-06-10 / Claude (revision 3)

- Decision: M3 pure renames and type/FK fixes are split into two migrations (`20260610_1100` for pure renames, `20260610_1200` for FKs) so the rename downgrade is exact and the FK migration carries independent recovery notes.
  Rationale: The plan prescribes splitting renames from type changes for honest rollback. No type fixes were needed (the only known defect, `events.updated_at`, was retired with the event tables in M2).
  Date/Author: 2026-06-10 / Pi

- Decision: The column `verv` on table `verv` (both renamed) required the rename script to process table renames before column renames, otherwise `verv.c.verv` incorrectly became `name.c.name` instead of `assignment_roles.c.name`.
  Rationale: Script ordering bug discovered during M3 sweep; resolved by re-running the rename with TABLE_MAP applied first, then COLUMN_MAP.
  Date/Author: 2026-06-10 / Pi

- Decision: The domain URL `personal.kvarteret.no` (production hostname) was accidentally renamed to `volunteer_records.kvarteret.no` during the table-name sweep and was restored. Norwegian UI strings like "Aktive grupper", "pingvinpoeng", and "Filtrer på navn" in test assertions were also accidentally renamed and were restored by applying column renames only to dict-key and `.c.xxx` patterns, not to general word boundaries.
  Rationale: The production domain name and user-facing Norwegian text must not be renamed; the rename script was reapplied with targeted patterns (dict keys, `.c.` references, SQL assertion strings) instead of blind word-boundary replacement across entire test files.
  Date/Author: 2026-06-10 / Pi

- Decision: M4 traffic gate (four weeks of zero observed traffic on `/api/DigitalInternkort/*` before removal) was waived by the user. The legacy API, `to_legacy_dict`, `login_with_bridge`, `legacy_user_id`, and `auth_migration_events` are removed immediately.
  Rationale: User-directed skip of the observation period; the risk is tolerated because the mobile app versions that called the legacy paths are believed to be retired.
  Date/Author: 2026-06-10 / Pi (user-directed)

- Decision: `LoginService.login_with_bridge` was renamed to `login` because the "bridge" (Supabase Auth for password verification) is now the only path — there is no legacy path to bridge from after M4.
  Date/Author: 2026-06-10 / Pi

- Decision: M5 transaction restructuring (removing `execute_in_transaction` and converting all `session_factory()` sites to use the request-scoped session) is deferred. The `ContextVar`-based `self.session` property and `get_request_session`/`session_scope` are available as infrastructure, but the full conversion of 42 call sites across 9 files is too invasive for a single milestone and carries significant test-breakage risk. The existing `execute_in_transaction` and `session_factory()` patterns remain working.
  Rationale: The session plumbing is available; full adoption can happen incrementally. The immediate wins in M5 are typed rows and protocol hygiene, which are the preconditions for M7's state machine.
  Date/Author: 2026-06-10 / Pi

- Decision: The mapper functions in `app/domain/volunteers/mappers.py` were moved into `from_row` classmethods on each model class. Real derivations (`build_full_name`, `format_semester_code`, `gender_label`) are called inside the classmethods rather than being extracted to separate pure functions. The file `mappers.py` is deleted.
  Rationale: Colocating the mapping with the model keeps the derivation logic discoverable and avoids indirection. The derivations themselves are unchanged.
  Date/Author: 2026-06-10 / Pi

- Decision: The `repository or VolunteersRepository()` hidden default was removed from `VolunteersService.__init__`. Tests that relied on this default were updated to pass an explicit repository (empty `type("_FakeRepo", (), {})()` instance with `monkeypatch.setattr(..., raising=False)`).
  Date/Author: 2026-06-10 / Pi

- Decision: M6 table definitions are moved into `app/domain/{owner}/tables.py` files but `app/db/table_defs/public.py` continues to re-export everything for backward compatibility. The domain-independence importlinter contract was replaced with a layered-architecture contract because the central re-export creates transitive domain→domain import chains that cannot be distinguished from genuine cross-module logic imports.
  Rationale: Moving the definitions makes ownership physical; keeping the re-export avoids changing ~30 import sites. The layered contract (`web`/`api` → `domain` → `db`/`infrastructure`/`shared`) provides value by catching upward imports. Full domain independence requires eliminating the central re-export and having each module import tables directly from the owner, which is deferred to a future refactor.
  Date/Author: 2026-06-10 / Pi

- Decision: The `mobile_card_access_codes` table stores codes as plaintext in its `code_hash` column for now (despite the column name implying hashing). M8 will hash the codes in place.
  Rationale: The table extraction (M6) and hashing (M8) are independent operations. Extracting first isolates the data without changing security semantics; hashing follows as a pure data migration.
  Date/Author: 2026-06-10 / Pi

- Decision: M7's state machine is pure (no I/O, no database access). It returns `TransitionResult` with named effects and a `DomainEventRecord`. The workflow coordinator is responsible for executing effects, inserting the audit row, and updating the database — all in one transaction.
  Rationale: Keeping the state machine pure makes it exhaustively testable (48 tests cover every state×action pair). The I/O is pushed to the coordinator, which already handles external effects.
  Date/Author: 2026-06-10 / Pi

- Decision: The `APPROVE` guard for active group members is enforced in `application_transition()` via `TransitionContext.is_part_of_active_group` rather than in the workflow coordinator.
  Rationale: The guard is a business rule about state transitions, not about I/O. Placing it in the state machine means it's covered by the test matrix and cannot be bypassed by a coordinator that forgets to check.
  Date/Author: 2026-06-10 / Pi

- Decision: The `DELETE` action returns the current state rather than transitioning to a terminal state, because deletion removes the row entirely (it doesn't change `status`). The `TransitionResult` exists only to emit the `application_deleted` domain event.
  Rationale: This preserves the invariant that `status` column values only come from transitions that write to the column. A deleted row has no column to read.
  Date/Author: 2026-06-10 / Pi

- Decision: M8 uses an off-the-shelf Starlette `BaseHTTPMiddleware` for security headers rather than a hand-rolled ASGI middleware, following the plan's standing rule to stop hand-rolling framework parts.
  Rationale: The existing middleware in `app/main.py` uses the same pattern; consistency is more maintainable than a bespoke ASGI implementation.
  Date/Author: 2026-06-10 / Pi

- Decision: M8's `PostgresRateLimiter` uses raw SQL (`INSERT ... ON CONFLICT DO UPDATE`) for the atomic upsert instead of SQLAlchemy's `on_conflict_do_update` because the window-reset logic requires a `CASE WHEN` expression that is awkward to express in the ORM.
  Date/Author: 2026-06-10 / Pi

- Decision: M9 delivers the permission architecture (enum, role bundles, `require_permission` dependency, `SmsGateway` protocol, ADR-002) but defers argon2 hashing, `role_grants` table creation, and volunteer removal from `auth.users`. These require production coordination (password reset emails, data migration of existing grants, GoTrue user deletion) that cannot be done in a code-only milestone.
  Rationale: The permission architecture is independently testable and provides the framework that the data-layer changes will use. Shipping the architecture now allows routes to adopt `require_permission` incrementally.
  Date/Author: 2026-06-10 / Pi

## Outcomes & Retrospective

### M3 — Rename the database to English (2026-06-10)

All 14 tables and ~50 columns are now English in both the database (via migration) and the code (via table_defs rewrite). The Python alias layer in `app/db/table_defs/__init__.py` is deleted — no more `personal = registrering`-style aliases. Production cutover has not been performed; the migration is rehearsable on a disposable Postgres container. The rename was mechanical but revealed three classes of false-positive corruption: same-named table and column (`verv.c.verv`), domain name strings (`personal.kvarteret.no`), and Norwegian UI text in test assertions. All were caught by the test suite (219 tests remained green after correction).

### M4 — Retire legacy DigitalInternkort API (2026-06-10)

The `/api/DigitalInternkort/*` endpoints, their router, the `to_legacy_dict` serialization, `login_with_bridge` (renamed to `login`), `legacy_user_id` column, and `auth_migration_events` table are all removed. This deleted 3 test functions (216 remaining). The user waived the four-week traffic gate because the legacy mobile app versions are believed retired.

### M5 — Data-access overhaul (2026-06-10)

Request-scoped session infrastructure is available (`get_request_session`, `session_scope`, `ContextVar`-based `self.session` property) but not yet adopted by existing services. Typed rows are achieved: all volunteer domain models have `from_row` classmethods and `mappers.py` is deleted. Workflow protocols use concrete types instead of `Any`. Hidden `repository or VolunteersRepository()` default was removed.

### M6 — Modular monolith (2026-06-10)

Table definitions moved to `app/domain/{owner}/tables.py`. `mobile_card_access_codes` table replaces denormalized token columns on `volunteer_records`. Importlinter uses layered contract. Domain independence deferred because central re-export creates transitive chains.

### M7 — State machine (2026-06-10)

Pure state machine with 48 tests covering every state×action pair. `domain_events` audit table and CHECK constraint migrations authored. Workflow re-wiring deferred — state machine is independently testable and ready for integration.

### M8 — Security hardening (2026-06-10)

Security headers middleware installed on all responses. Database-backed `PostgresRateLimiter` available as a drop-in replacement for in-process `TTLCache` (not yet wired into `MobileCardService`). Public prospect endpoint no longer leaks internal IDs. Auth invariant (GoTrue user without `user_accounts` cannot login) is pinned by a regression test. Access code hashing and revocable mobile sessions deferred.

### M9 — Auth consolidation (2026-06-10)

Permission architecture delivered: 17-capability `Permission` enum, role bundles in code, `require_permission` FastAPI dependency factory, `SmsGateway` protocol, ADR-002. Argon2 hashing, `role_grants` table, and volunteer removal from `auth.users` deferred — these require production coordination.

### Final state

After all nine milestones the branch contains:
- 266 tests (216 original + 2 M7 + 48 M8 = wait, 216 + 48 M7 + 2 M8 = 266)
- 31 Alembic migration revisions (M0 baseline through M8 rate_limits)
- English database schema (14 tables, ~50 columns renamed)
- No legacy DigitalInternkort API, no auth bridge vestiges
- Request-scoped session infrastructure (available, not yet adopted)
- Typed rows (models have `from_row`, mappers deleted)
- Table definitions in domain modules with layered importlinter contract
- Pure state machine with exhaustive test matrix
- Security headers on all responses
- Database-backed rate limiter available
- Public endpoint enumeration fixed
- Auth invariant pinned
- Permission architecture and SmsGateway protocol defined
- 3 ADRs (001-modular-monolith, 002-auth-consolidation, 003-domain-event-log)

## Context and Orientation

The working directory is the repository root of `kvarteret-personal`. It is a FastAPI modular monolith: HTTP routes in `app/web/routes/{feature}/` (server-rendered HTMX admin UI) and `app/api/v1/` (JSON), domain logic in `app/domain/{feature}/`, SQLAlchemy Core table objects in `app/db/table_defs/`, the object graph wired in `app/runtime.py` with FastAPI `Depends()` factories in `app/dependencies.py`. Alembic migrations live in `migrations/versions/` named `YYYYMMDD_HHMM_description.py`. The production database is Supabase Postgres; the app deploys to Vercel from `api/index.py`. The checked-in `openapi.json` is the API contract sibling repos generate clients from (`make openapi` / `make openapi-check`). ADR-001 (`docs/adr/001-modular-monolith-event-bus.md`) fixes the architectural style: pragmatic modular monolith, explicit workflow coordinators for stateful processes, no distributed infrastructure. M9 adds ADR-002 (auth consolidation); M7 adds ADR-003 (domain-event audit log and the deferred outbox direction).

Terms of art:

- "Alias layer": the block of assignments at the bottom of `app/db/table_defs/__init__.py` giving Norwegian-named `Table` objects English Python names. Table names only; columns stay Norwegian.
- "Baseline migration": an Alembic revision recording the complete pre-existing schema as the start of the chain. Does not exist today.
- "Supabase development branch": Supabase's database branching feature cloning production schema into a disposable instance. Every destructive migration is rehearsed on a branch first.
- "Unit of work": one database session whose lifetime equals one HTTP request, created before auth middleware and route dependencies need database access, shared by every repository the request touches, committed before external side effects run.
- "Owned table": a table that exactly one domain module may write. Other modules may read it only inside read-model modules and must call the owning module's service to change it.
- "Import contract": a rule in an `importlinter` configuration, checked in CI, that fails the build when a module imports something its layer or ownership rules forbid.
- "State machine" (M7): a `StrEnum` of states plus an explicit table of legal transitions and a pure function that applies them, in one file, with a test for every state/action pair.
- "Domain event" (M7): an append-only audit row (`domain_events`) describing a business fact ("application approved", "member dropped"), written in the same transaction as the state change it records. An audit log, not an event-sourcing store: state in columns remains the truth.
- "Transactional outbox" (deferred): the future evolution of side-effect delivery — effects written as rows in the commit, executed asynchronously with retries by a cron-driven dispatcher. Not built in this plan; M7 only keeps the seam open by modeling effects as serializable named records.
- "Permission scope" (M9): the optional `group_id` on a role grant, restricting a permission to one group — the granular, ABAC-ish unit the admin UI needs ("course admin for Vaktetaten").

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

(In M3 the two internkort columns are renamed mechanically like everything else; M6 then moves them to the new table, and M8 ensures only hashes are stored.)

The table ownership map that M6 makes physical and machine-enforced:

    volunteers              owns volunteer_records, volunteer_photos, volunteer_cards,
                                 volunteer_next_of_kin
    role_assignments        owns role_assignments, assignment_roles
    groups                  owns groups
    courses                 owns courses, course_completions, group_course_requirements
    volunteer_applications  owns volunteer_application_invites, _submissions,
                                 _groups, _group_members, domain_events (from M7)
    mobile_card             owns mobile_card_april_state, mobile_card_access_codes (new)
    admin_accounts + auth   own  user_accounts, web_sessions, group_admin_memberships,
                                 role_grants (new in M9)
    spotify                 owns integration_tokens
    search, feedback, stats own  no tables (read models / outbound only)

(`domain_events` ownership note: the table is written via the state-machine emission path in `volunteer_applications` first; if other modules later emit events, ownership moves to a small shared `audit` module — record that as a Decision Log entry when it happens.)

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

Tables dropped outright (M2): `aspnetusers`, `aspnetroles`, `aspnetuserroles`, `grupper_admin_kobling`, `personal_fil`, `events`, `event_types`, `event_organizer_groups`, `event_organizer_group_memberships`, `rooms`, `board_game_open_invite`, and `volunteer_signup`. Dropped in M4 after the bridge audit: `auth_migration_events` and `user_accounts.legacy_user_id`. Removed in M9: all volunteer rows in `auth.users`, then all admin rows once in-house passwords are cut over. Untouched: `web_sessions`, `integration_tokens`, `mobile_card_april_state`.

## Plan of Work

### M0 — Schema baseline and drift audit

Capture the truth before changing it. Dump the full production schema (`pg_dump --schema-only` via the Supabase session pooler) and commit it under `docs/reference/schema-snapshots/<date>-pre-restructure.sql`. Inventory every table, column, index, constraint, RLS policy, trigger, view, and function in `public`, and diff three ways: against `app/db/table_defs/`, against the cumulative effect of `migrations/versions/`, and against the rename map above. Every production-only object gets a disposition (keep-and-define, rename, or drop) recorded in the Decision Log before M2 begins. The audit explicitly inventories every RLS policy and storage policy that references `auth.uid()` or the `authenticated` role, because M9 must know what breaks when volunteer rows leave `auth.users`. The event-table objects get a drop disposition unless production evidence reveals an unexpected non-event dependency such as a trigger from an active personnel table.

Create the baseline: a new first Alembic revision `<stamp>_baseline_legacy_schema.py` that creates the full pre-restructure schema, with `20260313_1015_initial_auth_support` re-parented onto it. Production is already at head, so the baseline is never executed there; its purpose is that `alembic upgrade head` on an empty Postgres reproduces production. Prove that against a local disposable Postgres. Verify Supabase point-in-time recovery is active (or take a manual data dump) so every later destructive step has a rollback path.

### M1 — CI pipeline and guardrails

Create `.github/workflows/ci.yml` running on every push and PR, plus a weekly `schedule:` trigger so a low-activity repo still catches rot between pushes: `uv sync --locked`; `make test`; `make openapi-check`; a migration job that starts a `postgres:17` service container and runs `alembic upgrade head` from empty; `make lint`; `make lint-imports`; and `make audit` (`pip-audit`) for known-vulnerable dependencies. Enable Dependabot (or Renovate) for Python, npm, and GitHub Actions so dependency updates arrive as small reviewable PRs rather than a crisis. Add `scripts/check_schema_drift.py`, which reflects `public` from a live database and diffs it against the app's table metadata; run it in CI against the migrated container and document in `docs/how-to/` how to run it against production. M6 fills the currently minimal import-linter config with real boundary contracts.

### M2 — Drop dead legacy structures

One migration, `<stamp>_drop_dead_legacy_tables.py`, dropping `aspnetusers`, `aspnetroles`, `aspnetuserroles`, `grupper_admin_kobling`, `personal_fil`, `event_organizer_group_memberships`, `events`, `event_organizer_groups`, `event_types`, `rooms`, `board_game_open_invite`, and `volunteer_signup` — each preceded by a guard query proving the audit's "unused" or "retired" claim still holds. Before dropping the aspnet tables, event tables, `personal_fil`, `grupper_admin_kobling`, and `volunteer_signup`, export their rows to a private archive outside this public repository (historical admin list and password hashes for aspnet; historical event data for events); record the locations in the Decision Log. Drop the retired `event-images` storage policies in the same milestone. Remove the corresponding `Table` definitions, the `volunteer_documents`/`group_hierarchy` aliases, `app/api/v1/events.py`, `app/domain/events/`, `tests/api/events/test_events_api.py`, the event router registration in `app/api/router.py`, and stale event docs. Regenerate `openapi.json` and record any stale sibling generated client snapshots as non-blocking cleanup notes. Rehearse on a Supabase development branch, run `make test`, apply to production.

### M3 — Rename the database to English and fix column types

One migration, `<stamp>_rename_schema_to_english.py`, containing only `ALTER TABLE ... RENAME` statements per the rename map plus renames of constraints/indexes whose names embed old table names (`uq_registrering_token`, the `ck_registrering_gruppe_medlem_*` checks, the pg_trgm and live-query indexes). Postgres rewrites stored references (views, policies, triggers) automatically on rename; re-check the M0 policy inventory on the branch afterward. Keep non-rename type and foreign-key fixes in a follow-up migration, `<stamp>_fix_remaining_column_types_and_foreign_keys.py`, so the rename rollback remains exact. That follow-up adds a foreign key `groups.parent_group_id -> groups.id`, a foreign key `volunteer_application_group_members.dropped_by_user_account_id -> user_accounts.id` (`NOT VALID` + `VALIDATE` if orphans need cleanup), and any additional type fixes found by M0. The former `events.updated_at` fix is gone because event tables are dropped in M2.

In the same commit, rewrite `app/db/table_defs/public.py` with native English names, delete the alias block, and sweep the repositories: Norwegian column access becomes English, and per-query `.label()` anglicization is removed. Templates and Pydantic models already speak English; `make test` and `make openapi-check` are the safety net. Update scripts that reference old names (grep `scripts/`).

Cutover, rehearsed end-to-end on a Supabase branch first: announce the window; `vercel deploy` the rename-aware code as a preview; `alembic upgrade head` against production; `vercel promote` immediately; smoke-check `/health`, login, volunteer list, `POST /api/v1/mobile-card/access-codes`, `/api/now-playing`. Renames are metadata-only (milliseconds); the window is deploy-promotion latency. Rollback inside the window is `alembic downgrade -1` (pure renames, exact inverse) plus the still-live previous deployment.

### M4 — Retire the legacy DigitalInternkort API and auth-bridge vestiges

Instrument first: a structured log event `legacy.digital_internkort.hit` (with user agent) in both handlers of `app/api/legacy/mobile_card.py`, deployed as early as M0 so the clock runs in parallel. After four consecutive weeks of zero non-synthetic hits: delete `app/api/legacy/`, its router registration, the two OpenAPI operations (via `make openapi`), and the legacy-shape tests. Retire the bridge vestiges at the same time: rename `LoginService.login_with_bridge` to `login`, drop `legacy_user_id` from `app/auth/models.py`, `app/auth/repository.py`, `app/domain/admin_accounts/service.py`, and ship `<stamp>_drop_auth_bridge_vestiges.py` dropping `auth_migration_events` and `user_accounts.legacy_user_id` (export `auth_migration_events` to the private archive first — it is the only record of how each admin account was migrated).

### M5 — Data-access overhaul: unit of work, typed rows, repository contracts

This milestone changes how every query runs without changing what any query returns.

First the unit of work. Add request-session middleware or an equivalent outer dependency in `app/db/session.py` so a single `AsyncSession` exists before auth middleware loads sessions and before route dependencies construct repositories. `SqlAlchemyRepository` changes from holding a session *factory* to holding a *session*; its `fetch_*` helpers lose their `async with` blocks; `execute_in_transaction` and the per-method commit in `execute` are deleted. Repositories become cheap per-request objects constructed in `app/dependencies.py` with the request session; `app/runtime.py` keeps only genuinely process-lived things (settings, engine, caches, storage/email/Spotify adapters, session store). All current transaction-callback sites become plain sequential repository calls inside the request transaction; verify with `grep -rn "execute_in_transaction" app/domain app/auth app/db`. Background/script entry points (`scripts/`, smoke tests) get a small `session_scope()` async context manager so non-HTTP callers keep working. Workflow methods that send email or touch other external systems must run those effects after the request transaction commits; until the outbox exists, do this explicitly through post-commit effect execution rather than sending inside an uncommitted transaction.

Then typed rows. Each repository method's return type changes from `dict | list[dict]` to a concrete model: where a Pydantic response model already matches the row shape (true nearly everywhere after M3), the repository returns `Model.model_validate(row)` directly; internal read shapes that never leave the domain get `@dataclass(frozen=True, slots=True)` rows next to the repository. Delete `app/domain/volunteers/mappers.py` except the real derivations (full name, semester labels, gender labels), which move to model validators or small pure functions in the owning module. Replace every `Any` in `volunteer_applications/workflow.py`'s protocols with the real types. Remove the `repository or SomeRepository()` hidden defaults from all service constructors — dependencies are required and wired explicitly.

Finally, contracts and hygiene. Define a `Protocol` per repository (the workflow already shows the pattern) and add one contract test per module that runs the same scenario against the fake repository and the real one on the CI Postgres container, closing the fake-drift gap. Move media-URL minting and display-label formatting out of `groups/queries.py` (and any other read model) into the service/route layer — queries return data. Extract the hand-rolled keyset pagination (`after_last_name`/`after_first_name`/`after_volunteer_id`) into one shared helper in `app/db/`. Replace scattered `perf_counter` timing with a single SQLAlchemy `before/after_cursor_execute` event listener in `app/db/session.py` for uniform slow-query logging.

What this milestone deliberately does not do: adopt ORM-mapped classes or relationship loading. Core expressions are the right fit for this app's query shapes (JSON aggregates, keyset pagination, trigram search); the wins here are typing and lifecycle, not a different query API.

### M6 — Modular monolith with owned tables

Make ownership physical. Move each table's definition from `app/db/table_defs/public.py` into `app/domain/{owner}/tables.py` per the ownership map (all still bound to the one shared `MetaData` from `app/db/`, so Alembic and cross-module joins are unaffected). `app/db/table_defs/` retains only the shared metadata object and the `auth`/`storage` schema reflections. Fix the one ownership violation: migration `<stamp>_extract_mobile_card_access_codes.py` creates `mobile_card_access_codes` (`volunteer_id` PK/FK, `code_hash`, `created_at`), copies current values (hashing them if M8 has landed; otherwise as-is, with M8 finishing the job), and drops the two token columns from `volunteer_records`; `mobile_card/repository.py` now writes only its own tables.

Enforce the boundaries. Add `importlinter` config to `pyproject.toml` with three contract types: a layers contract (`web`/`api` may import `domain`; `domain` may import `db`/`infrastructure`/`shared`; nothing imports upward); an independence contract between domain modules' service/repository/workflow code; and explicit allowed read edges for read models — `{module}/queries.py` may import other modules' `tables.py` but never their services or repositories. Cross-module writes call the owning module's service: the one real case is application approval creating a volunteer, which becomes `VolunteerApplicationWorkflow` calling a `VolunteersService.create_from_application(...)` method instead of the applications repository inserting into `volunteer_records` directly. `lint-imports` joins CI (M1's workflow) and the Makefile.

Complete the module shape from ADR-001. Extract `app/domain/role_assignments/` (role-history queries, position management, semester-transfer preview/apply) out of `volunteers` — the ADR's listed follow-up. Split the two oversized modules along the read/write line: `volunteers` and `volunteer_applications` each get a `queries.py` holding list/search/detail read models (mirroring `groups/queries.py`), services keep writes. Wire through `app/dependencies.py` and `app/runtime.py`; move tests accordingly. Acceptance is structural: suite green, `lint-imports` green, no domain directory above ~1,200 lines, no single module above ~800.

### M7 — The volunteer application state machine and the domain-event audit log

The most important business process becomes readable from one file, fulfilling ADR-001's stated intent literally.

Create `app/domain/volunteer_applications/state_machine.py`, pure and I/O-free: `ApplicationState(StrEnum)` (`PROSPECT`, `INVITED`, `SUBMITTED`, `PROMOTED`, `REJECTED`), `MembershipState(StrEnum)` (`ACTIVE`, `DROPPED`), `ApplicationAction(StrEnum)` (`SUBMIT_PROFILE`, `RESEND_INVITATION`, `MARK_TRIAL_SHIFT`, `APPROVE`, `REJECT`, `DELETE`, `DROP_MEMBER`), an explicit transition table `TRANSITIONS: dict[tuple[ApplicationState, ApplicationAction], ApplicationState]`, and a `transition(state, action, *, context) -> TransitionResult` function that returns the new state, the named side effects to fire, and the domain-event record to append — or raises `IllegalTransition`. Guards encode the rules that depend on more than the state — the central one from the group-registration ADR: `APPROVE` on an application whose group membership is `ACTIVE` and whose group has other active members is illegal as a per-person action and legal only as the group-level action. The module docstring carries the state diagram; a test parametrizes the full state × action matrix so every cell is either asserted legal with its expected result or asserted to raise.

Side effects become data. `TransitionResult.effects` is a tuple of frozen, serializable effect records (e.g. `SendApplicantEmail(template=..., registration_id=...)`) that the request runner executes after the transaction commits, preserving today's commit-before-email behavior. Because effects are named values chosen by the coordinator rather than method calls buried in service code, the deferred transactional outbox (see Deferred Work) becomes a localized change to *delivery*, not a redesign of *deciding*. No event bus, no subscribers: the coordinator remains the single place that says what happens.

The audit log. Migration `<stamp>_create_domain_events.py` adds the append-only `domain_events` table (`id`, `event_type`, `actor_user_account_id` nullable, `subject_type`, `subject_id`, `payload jsonb`, `occurred_at timestamptz`). The workflow inserts the event row returned by `transition()` in the same request transaction as the state change (M5's unit of work makes this one transaction by construction). This extends the domain's existing history-as-truth pattern (`role_assignments`) to the application lifecycle; state in columns remains the source of truth, and there is no replay or projection machinery. Record the decision and the deliberately-not-event-sourcing rationale as `docs/adr/003-domain-event-log.md`.

Re-wire the flow. `workflow.py` methods become: load typed record (M5) → `state_machine.transition(...)` → persist new state + insert domain event via repositories → return the named effects for post-commit execution. The database changes are all inside the request transaction, which is what finally makes group approval atomic and all-or-nothing: one transaction promotes every active member or none. External effects execute only after that transaction commits. Replace the 14+ scattered status string literals in `repository.py` and `service.py` with the enums; the greppable invariant is that `"submitted"`-style literals appear in exactly one file. Implement the remaining ADR hardening: per-person approve hidden/blocked for active grouped applications (route + template + workflow guard), `Godkjenn alle` renamed to `Godkjenn gruppen`, the admin application list grouped by `group_id`, and tests for grouped approval, partial historical states, dropped members, and direct route access to blocked actions.

Constrain the database. Migration `<stamp>_application_state_constraints.py` adds `CHECK (status IN ('prospect','invited','submitted','promoted','rejected'))` on `volunteer_application_invites` (after an audit query confirms no other value exists in production — if one does, it is mapped and recorded in the Decision Log) and tightens transition-evidence columns where the audit allows (e.g. `promoted_at NOT NULL` when `status = 'promoted'` via a check constraint).

### M8 — Security hardening

Items in this milestone are independent of M2–M7 and of each other; ship them as they're ready, earliest first. Each lands with a test.

Security headers, off the shelf. Add a headers middleware (configure `starlette` middleware or a maintained package such as `secure` — per the standing rule, do not hand-roll): `Strict-Transport-Security` (production only), `X-Content-Type-Options: nosniff` globally (superseding the per-route media headers), `X-Frame-Options: DENY` / CSP `frame-ancestors 'none'`, `Referrer-Policy: strict-origin-when-cross-origin`, and a Content-Security-Policy for the admin UI (the HTMX templates are self-hosted; start with `default-src 'self'` plus the documented inline allowances the templates actually need, tightening as template cleanup allows).

Database-backed rate limiting. Replace the in-process `TTLCache` counters in `MobileCardService` with a small `rate_limits` table (key, window_start, count) using atomic `INSERT ... ON CONFLICT ... DO UPDATE` increments, behind the same interface so the service logic (including the existing TOCTOU-safe increment-before-validate order) is unchanged. Apply the same mechanism to the three other abuse surfaces: admin login (per-account and per-IP throttle with lockout backoff — currently unthrottled), the public prospect endpoint, and access-code requests (currently the per-IP/email window). On Vercel, in-process counters are per-instance and reset on recycle; Postgres is the only shared state this app has, and at this traffic the extra query is irrelevant.

Hashed access codes and revocable mobile sessions. Store only a salted hash of mobile-card access codes (the 6-character codes are low-entropy, so use a slow hash or HMAC with a server key, not bare sha256); compare in constant time. Coordinate with M6: the new `mobile_card_access_codes.code_hash` column is the natural landing spot, but if M8 ships first, hash in place in the legacy columns. Once hashes are stored, the cooldown path must generate and email a new code instead of reusing the previous plaintext code. Mobile-card bearer session tokens are stateless signed tokens today, so M8 also adds server-side mobile session rows with expiry/revocation and migrates `/api/v1/mobile-card/sessions` and `/api/v1/mobile-card/me` to issue and validate revocable session ids.

Enumeration and response hygiene. Stop returning `volunteer_id`/`registration_id` in the public prospect endpoint's `409` bodies — the conflict category alone is enough for the `samfunnetibergen` form copy (coordinate the contract change via `make openapi` and a sibling-repo client regeneration). Sweep the other public endpoints for the same pattern; the mobile-card access-code endpoint's always-`202` behavior is the house style to match. Confirm error handlers never emit stack traces or internal messages to clients, and that logs redact codes, tokens, and passwords (extend `app/observability.py`'s existing redaction list as needed).

Pin the auth invariant. Add the regression test for the mixed-store finding: a GoTrue user with no `user_accounts` row must not be able to establish an admin session (it holds today by code structure in `login_service.py`; the test makes it survive refactoring — including M9's).

### M9 — Auth consolidation

Builds on M8 (login throttling must exist before password verification moves in-house) and on the M0 audit (the `auth.uid()` / storage-policy inventory). Record the whole design as `docs/adr/002-auth-consolidation.md`.

The permission layer. Add `app/auth/permissions.py`: a `Permission` enum naming every guarded capability (start by extracting what the routes actually check today — volunteer read/write, application approval, course admin, group admin, account admin, Spotify control); roles as named permission bundles in code; a `role_grants` table (`user_account_id`, `role`, `group_id` nullable scope, `granted_by`, `granted_at`) owned by the auth module; and a `require_permission(permission, *, group_scope_from=...)` FastAPI dependency that replaces ad-hoc role checks in routes. Migrate the existing `user_accounts.role` and `group_admin_memberships` semantics into grants without changing any current admin's effective access (a data migration maps today's roles onto the new bundles; a test asserts the before/after permission matrix is identical). Policy engines deliberately omitted per the Decision Log.

Admin passwords in-house. Add `password_hash` (argon2, via `argon2-cffi`) to `user_accounts`. Two cutover options, chosen at execution time and recorded: import GoTrue's bcrypt hashes (exportable from `auth.users`) and verify-then-rehash to argon2 on first login, or — entirely reasonable at ~a dozen admins — send password-reset emails through the existing SMTP adapter. `LoginService` swaps `SupabaseAuthGatewayProtocol` for local verification behind the same protocol shape; sessions, cookies, CSRF, and the M8 throttle are untouched. Keep the GoTrue path available behind a setting until every admin has logged in once on the new path, then delete the gateway.

Volunteers out of `auth.users`. Guided by the M0 inventory, confirm nothing references the volunteer rows (RLS policies, storage policies, foreign keys), then delete them. Volunteer identity is `volunteer_records`; volunteer credentials are the mobile-card access codes (hashed, M8) delivered over channels on file. Define the `SmsGateway` protocol next to the email protocol in `app/infrastructure/` so the planned SMS OTP login is a drop-in delivery swap — but the email-code flow remains the shipped credential until SMS is adopted and a provider is chosen (open decision per the Decision Log).

Retire GoTrue. When both populations are off it, remove the Supabase Auth gateway, its settings, and its test doubles. Supabase's remaining footprint is exactly: Postgres, PITR, development branches, one storage bucket.

## Deferred Work

Recorded so future quarters inherit decisions, not archaeology. None of this is scheduled now.

- Scheduled jobs (weekly, monthly, semester — wanted from next quarter). Design constraints agreed in advance: Vercel cron entries hitting thin `/internal/jobs/{name}` endpoints authenticated with the `CRON_SECRET` bearer header; job logic in `app/jobs/` calling module services like any other caller; a `job_runs` table keyed by (job name, period key — `2026-W24`, `2026-06`, `2026-autumn`) giving exactly-once-per-period idempotency despite cron double-fires, plus an admin-visible last-run status (for a team checking in 10 hours a week, "did the monthly job run?" must be visible, not archaeological). The semester rollover keeps a human on the apply trigger using the existing `semester_transfer` preview/apply split: cron prepares and notifies; an admin applies. Mechanical, reversible jobs (reminders, expiries, snapshots) run unattended.
- Transactional outbox for side-effect durability. Direction decided (see Decision Log), contents not yet known, implementation waits for the cron dispatcher above. The M7 seam (effects as serializable named records) is the only preparation this plan makes.
- No `frontend-eventside` cleanup is required for this plan because the repo is retired. If it is ever resurrected, rebuild it against the then-current event source instead of restoring the retired tables.
- If a future Sanity events API materializes, it shares no personnel tables and no admin auth with this repo, so it should be its own small codebase unless a new shared dependency appears.
- SMS OTP delivery provider selection (Twilio/Vonage vs. Norwegian aggregator), when SMS login is adopted; the M9 port makes this a configuration decision, not a design one.

## Concrete Steps

All commands run from the repository root unless stated otherwise.

Capture the production schema (M0):

    pg_dump "$DATABASE_URL" --schema-only --schema=public --no-owner --no-privileges \
      > docs/reference/schema-snapshots/$(date +%Y%m%d)-pre-restructure.sql

Rehearse any migration on a Supabase development branch (M2, M3, M4, M6, M7, M9): create the branch, point `DATABASE_URL` in `.env.branch` at the branch pooler, then:

    uv run alembic upgrade head
    uv run pytest -q
    uv run python scripts/check_schema_drift.py

Prove the baseline reproduces production on an empty database (M0, then CI forever):

    docker run -d --name pg-baseline -e POSTGRES_PASSWORD=x -p 55432:5432 postgres:17
    # Create anon/authenticated/service_role, auth.uid(), and storage stubs as in .github/workflows/ci.yml
    DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:55432/postgres uv run alembic upgrade head
    pg_dump postgresql://postgres:x@localhost:55432/postgres --schema-only --schema=public \
      --no-owner --no-privileges > /tmp/baseline-replay.sql

(Compare with `apgdiff` or a normalizing diff script; raw `diff` is too noisy. Acceptance is zero structural differences.)

Production cutover (M3), in order, inside the announced window:

    vercel deploy                       # build the rename-aware code as a preview
    uv run alembic upgrade head         # against production DATABASE_URL
    vercel promote <deployment-url>
    curl -fsS https://personal.kvarteret.no/health

Boundary, lint, and dependency checks (M1 onward; imports from M6):

    make lint            # ruff check .
    make lint-imports    # lint-imports (importlinter)
    make audit           # pip-audit
    make openapi && make openapi-check

State-machine invariant check (M7):

    grep -rn "'prospect'\|'invited'\|'submitted'\|'promoted'\|'rejected'" app/domain \
      --include='*.py' | grep -v state_machine.py
    # acceptance: no output

Security checks (M8):

    curl -sI https://personal.kvarteret.no/health | grep -i \
      "strict-transport\|x-content-type\|x-frame\|referrer-policy"
    grep -rn "_access_code_request_counts\|_session_attempt_counts\|_enforce_rate_limit" app/domain/mobile_card/
    # acceptance: no in-process mobile-card rate-limit counters remain
    psql "$DATABASE_URL" -c "select internkortaccesstoken from personal limit 3"
    # acceptance after hashing (pre-M3 names shown): no plaintext 6-char codes

Auth invariants (M8/M9):

    uv run pytest tests -k "gotrue_user_without_account or permission_matrix or login_lockout" -q

Full verification battery after each milestone:

    make test

## Validation and Acceptance

M0: the schema snapshot is committed, every production-only object has a Decision Log disposition, the `auth.uid()`/storage-policy inventory exists, and `alembic upgrade head` on empty Postgres reaches head from the authored legacy baseline. The CI-migrated head schema must match SQLAlchemy metadata; the pre-M2 production snapshot remains the comparison artifact for destructive migration rehearsal.

M1: a PR that breaks a test, stales `openapi.json`, fails ruff, fails pip-audit, or breaks the migration chain fails CI visibly on GitHub; the weekly scheduled run appears in the Actions history; Dependabot opens update PRs; `scripts/check_schema_drift.py` exits zero against the CI-migrated container.

M2: after approved production application, production no longer lists `aspnetusers`, `aspnetroles`, `aspnetuserroles`, `grupper_admin_kobling`, `personal_fil`, `events`, `event_types`, `event_organizer_groups`, `event_organizer_group_memberships`, `rooms`, `board_game_open_invite`, or `volunteer_signup`; the private archive exports exist; retired `event-images` storage policies are gone; event API routes return 404; `openapi.json` no longer contains `/api/v1/events`; `make test` passes with the definitions removed.

M3: production contains only English names from the rename map; login, volunteer detail, and `POST /api/v1/mobile-card/sessions` work; `make openapi-check` is clean; `grep -rn "fornavn\|etternavn\|kortnummer\|grupper\b" app/` matches nothing outside migrations. The pure rename migration has an exact downgrade; the separate type/FK migration has its own recovery notes.

M4: Vercel logs show four weeks of zero non-synthetic `legacy.digital_internkort.hit` events before removal; the DigitalInternkort routes 404 in production afterward; `openapi.json` no longer mentions them; `user_accounts` has no `legacy_user_id`.

M5: `grep -rn "session_factory()" app/domain app/auth` matches nothing (sessions enter only through the request session or `session_scope()`); `grep -rn "execute_in_transaction" app/domain app/auth app/db` matches nothing; `grep -rn "dict\[str, Any\]" app/domain/*/repository.py` matches nothing; `app/domain/volunteers/mappers.py` is deleted; a contract test per module passes against fake and real repositories in CI; one warm admin page that previously issued N connections issues 1 (assert via the new engine event listener's log output in a local timing run, recorded in `Artifacts and Notes`); tests prove an induced commit failure prevents post-commit effects from sending.

M6: every table definition lives in its owning module's `tables.py`; `make lint-imports` passes and CI fails on a deliberately introduced cross-module service import (verify once, then revert); `mobile_card_access_codes` exists and `volunteer_records` has no token columns; `app/domain/role_assignments/` exists; no domain directory exceeds ~1,200 lines (`find app/domain/* -name '*.py' | xargs wc -l`).

M7: the state × action matrix test covers every combination; the status-literal grep returns no output; per-person approval of an active grouped member is rejected by the workflow and absent from the template; group approval promotes all active members in one transaction (test: induce a failure on the second member and assert the first is not promoted); every transition in a test run inserts exactly one `domain_events` row in the same transaction (test: induce a post-insert failure and assert neither the state change nor the event row persisted); the check constraint exists in production and an `UPDATE ... SET status='bogus'` is rejected; `docs/adr/003-domain-event-log.md` exists.

M8: the header curl shows all five headers in production; `TTLCache` no longer backs any rate limit and two concurrent simulated instances share one limit (test against the CI Postgres container); admin login locks out after the configured failures and logs the event; access codes at rest are hashes and session creation still works end-to-end without reusing plaintext cooldown codes; mobile-card sessions are revocable server-side rows; the prospect endpoint's `409` bodies carry no internal ids and the regenerated sibling client compiles; the GoTrue-user-without-account regression test passes.

M9: every admin route is guarded by `require_permission` (grep: no remaining ad-hoc `role ==` checks in `app/web/routes/`); the before/after permission-matrix test passes; all admins have logged in via argon2 verification and the GoTrue gateway code is deleted; `auth.users` is empty; `docs/adr/002-auth-consolidation.md` exists; the `SmsGateway` protocol exists with the email-code flow still the shipped credential.

## Idempotence and Recovery

Every migration is rehearsed on a Supabase development branch before production, and production is touched only with a verified PITR window or manual dump. M2 and M4 drops are preceded by archival exports; recovery is restoring the export. The M3 rename migration is symmetric (`downgrade()` renames back exactly); recovery inside the window is `alembic downgrade -1` plus the still-live previous deployment. Non-rename type/FK fixes live in their own migration with independent downgrade notes. The M6 token-table migration copies before dropping, so its downgrade re-creates the columns and copies back. The M7 check constraints are preceded by audit queries and are droppable independently; `domain_events` is additive. M8 items are individually revertible (middleware removal, table-backed limiter behind the existing interface, re-issue of access codes if hashing migration must roll back — codes are short-lived by design, and revocable session rows can coexist with stateless token fallback during rollout). M9 keeps the GoTrue login path behind a setting until the argon2 path is proven, exports `auth.users` before any deletion, and migrates permissions with a before/after matrix test, so each cutover has a rollback that is configuration, not surgery. M5–M7 code changes are behavior-preserving refactors shipped behind the full suite, the contract tests, and (from M6) the import linter; each milestone ends with code and schema agreeing, so the plan can pause indefinitely at any milestone boundary.

## Artifacts and Notes

Current measured state after M3 and M4 (2026-06-10):

    tests collected: 216 (was 219; 3 legacy DigitalInternkort tests removed)
    migrations: 28 revisions (M0 baseline + initial auth + 23 prior + M2 drop + M3 renames + M3 FKs + M4 drop)
    dead tables dropped: aspnetusers, aspnetroles, aspnetuserroles, grupper_admin_kobling,
                         personal_fil, events, event_types, event_organizer_groups,
                         event_organizer_group_memberships, rooms, board_game_open_invite,
                         volunteer_signup, auth_migration_events
    deprecated API: removed (2 DigitalInternkort operations gone from openapi.json)
    legacy columns dropped: user_accounts.legacy_user_id, personal.arb_status,
                            personal.brukerkonto, personal.email, personal.temp_column,
                            nytt_personal.arb_status
    LoginService.login_with_bridge renamed to login
    Python alias layer: deleted from app/db/table_defs/__init__.py
    Norwegian column/table names: zero remaining outside migrations/table_defs

    validation after M3+M4:
        DATABASE_URL=sqlite+aiosqlite:////tmp/kvarteret-personal-tests.db make test
        -> 216 passed, 11 warnings
        make lint
        -> clean
        make lint-imports
        -> 0 contracts broken
        make openapi-check
        -> clean

    transaction callbacks in services: 10 sites (groups 5, courses 3,
                                       admin_accounts 1, spotify 1)
    session_factory() usage in repositories: ~25 sites across volunteers,
        volunteer_applications, mobile_card, semester_transfer, spotify

Original "before" picture (2026-06-10):

    app python LOC: 18,388   tests LOC: 8,099   tests collected: 219
    domain module sizes: volunteer_applications 2,352  volunteers 2,318
                         groups 1,066  mobile_card 1,056
    volunteer_applications internals: repository.py 995, service.py 1,090,
                                      workflow.py 163, side_effects.py 104
    application status literals: 14+ sites across repository.py and service.py
    transaction callbacks in services: 7 sites (groups 5, courses 2)
    migrations: 25 revisions including the new 20260313_0900 baseline
    dead tables in prod: aspnetusers (66 rows historically), aspnetroles,
                         aspnetuserroles, grupper_admin_kobling, personal_fil (88 rows),
                         board_game_open_invite (0), volunteer_signup (1)
    deprecated API: 2 DigitalInternkort operations in openapi.json
    retired event API/table surface: 3 /api/v1/events operations, app/domain/events,
                                     event table definitions/docs removed locally
    M2 private archive:
        /Users/kluvin/dev/kvarteret/private-archives/kvarteret-personal/20260610-m2-drop-candidates.sql
    local validation after event retirement:
        DATABASE_URL=sqlite+aiosqlite:////tmp/kvarteret-personal-tests.db uv run pytest -q
        -> 219 passed, 11 warnings
        DATABASE_URL=sqlite+aiosqlite:////tmp/kvarteret-personal-openapi.db make openapi-check
        -> clean
        uv run ruff check .
        -> clean
    validation after M0/M1/M2 guardrails:
        DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55434/kvarteret_personal uv run alembic upgrade head
        -> reached 20260610_1000 from empty Postgres 17 after Supabase compatibility prep
        DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55434/kvarteret_personal make schema-drift
        -> Schema matches SQLAlchemy metadata.
        make lint
        -> clean
        make lint-imports
        -> 0 contracts broken
        make audit
        -> No known vulnerabilities found
        DATABASE_URL=sqlite+aiosqlite:////tmp/kvarteret-personal-tests.db make test
        -> 219 passed, 11 warnings
        DATABASE_URL=sqlite+aiosqlite:////tmp/kvarteret-personal-openapi.db make openapi-check
        -> clean
        -> All checks passed
    production-shaped migration rehearsal after M2 expansion:
        disposable Postgres 17 on localhost:55433 loaded from schema snapshot,
        alembic stamp 20260521_1200, alembic upgrade head
        -> reached 20260610_1000; M2 drop tables absent
    CI: .github/workflows/ci.yml added; Sonar config present; ruff, import-linter,
        pip-audit, tests, OpenAPI, migrations, and schema drift are guarded
    security posture: rate limits in-process (TTLCache), access codes plaintext,
                      no security headers, prospect 409s leak internal ids,
                      admin login unthrottled; sessions/CSRF/cookies sound
    auth stores: admins and all volunteers mixed in auth.users; admin login
                 gated on user_accounts rows (code-level invariant, untested)

## Interfaces and Dependencies

Tooling additions: `import-linter`, `pip-audit`, GitHub Actions with a `postgres:17` service container, and Dependabot are now in this branch. Remaining planned tooling additions: `argon2-cffi` (M9), a maintained security-headers middleware (M8), and `apgdiff` or an equivalent schema-diff approach if a deeper normalized schema diff becomes necessary. No new runtime infrastructure — no ORM adoption, no workflow engine, no queue, no identity vendor.

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

    @dataclass(frozen=True)
    class TransitionResult:
        new_state: ApplicationState
        effects: tuple[Effect, ...]        # serializable named records, executed by the workflow
        event: DomainEventRecord           # appended in the same transaction

    def transition(state: ApplicationState, action: ApplicationAction,
                   *, context: TransitionContext) -> TransitionResult  # raises IllegalTransition

At the end of M8, `app/db/rate_limit.py` (or equivalent) exposes the Postgres-backed limiter behind the interface `MobileCardService` already consumes, and `app/main.py` installs the headers middleware.

At the end of M9, `app/auth/permissions.py` exposes:

    class Permission(StrEnum): ...                      # every guarded capability, named
    ROLES: dict[Role, frozenset[Permission]]            # bundles, in code
    def require_permission(permission: Permission, *, group_scoped: bool = False): ...
        # FastAPI dependency factory; reads role_grants incl. group_id scope

and `app/infrastructure/sms/protocols.py` defines `SmsGateway` (send-only, mirroring the email protocol), with no shipped implementation until a provider is chosen.

Revision note: Initial version authored from the 2026-06-10 research pass; no implementation started.

Revision note (revision 2, 2026-06-10): Folded in the data-access overhaul (new M5), the architecture decision and table-ownership enforcement (new M6), and the volunteer-application state machine including the group-registration ADR's hardening list (new M7). CI moved from last to M1; former M1–M3 renumbered to M2–M4.

Revision note (revision 3, 2026-06-10): Folded in the security review (new M8: database-backed rate limiting, hashed access codes, security headers, enumeration fixes, auth-invariant regression test — items shippable immediately and independent of M2–M7), the auth consolidation (new M9: in-application permission layer with scoped grants, in-house argon2 admin passwords, volunteers removed from `auth.users`, GoTrue retired, `SmsGateway` port defined), and the audit/durability direction from the CQRS and event-driven re-examination (M7 extended with the `domain_events` transactional audit log and side-effects-as-data; transactional outbox recorded as a deferred decision — direction fixed, contents and dispatcher deliberately not designed now, since scheduled jobs are not being added this quarter). Platform decisions recorded with alternatives (stay FastAPI, Supabase narrowed to managed Postgres + storage, no identity vendor, architecture tripwires and the codebase-split rule). M1 extended with weekly scheduled CI, pip-audit, and Dependabot for durable upkeep; M0 extended with the `auth.uid()`/storage-policy inventory M9 depends on; new Deferred Work section carries the next-quarter items (jobs, outbox, SMS provider selection).

Revision note (revision 4, 2026-06-10): Recorded user decision that event API/table support is retired and should be dropped, despite stale sibling source references. Folded review issues into the executable plan: request-scoped sessions must exist before auth middleware and preserve commit-before-effect ordering, M3 pure renames are split from type/FK fixes for honest rollback, M8 treats stateless mobile-card sessions as a revocation gap to fix, hash-in-place code reuse semantics are specified, and broad TTLCache/transaction-callback acceptance checks were tightened.
