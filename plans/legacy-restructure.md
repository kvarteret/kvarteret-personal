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
- [ ] M0: Schema baseline and drift audit.
- [ ] M1: CI pipeline and guardrails.
- [ ] M2: Drop dead legacy structures.
- [ ] M3: Rename the database to English and fix column types.
- [ ] M4: Retire the legacy DigitalInternkort API and auth-bridge vestiges (traffic-gated; runs in parallel from M0 onward).
- [ ] M5: Data-access overhaul — request-scoped unit of work, typed rows, delete the mapper layer, repository contracts.
- [ ] M6: Modular monolith with owned tables — ownership map, import-linter boundaries, module extractions and splits.
- [ ] M7: Volunteer application state machine — pure transitions module, database constraints, atomic group approval, domain-event audit log.
- [ ] M8: Security hardening — database-backed rate limiting, hashed access codes, security headers, enumeration fixes. (Items are independent of M2–M7 and may ship at any time.)
- [ ] M9: Auth consolidation — in-application permission layer, in-house admin passwords, volunteers out of `auth.users`, GoTrue retired.

## Surprises & Discoveries

Findings from the research passes (2026-06-10). Update as implementation reveals more.

- Observation: The legacy ASP.NET Identity tables are dead code. `aspnetusers`, `aspnetroles`, and `aspnetuserroles` are defined in `app/db/table_defs/public.py` but nothing queries them. Migration `20260319_1215_drop_unused_legacy_identity_tables.py` already dropped the empty claims/logins/tokens tables and `__efmigrationshistory`, but kept these three.
  Evidence: `grep -rn "aspnet" app --include='*.py'` matches only `table_defs` and `tables.py`.

- Observation: Login no longer touches legacy password hashes. `app/auth/login_service.py` authenticates directly against Supabase Auth; the method is still named `login_with_bridge` but contains no bridge. `user_accounts.legacy_user_id` and `auth_migration_events` are write-only vestiges.

- Observation: `grupper_admin_kobling` is unused (replaced by `group_admin_memberships`), and its alias `group_hierarchy` in `app/db/table_defs/__init__.py` is a misnomer — group hierarchy actually lives in `grupper.id_overgruppe`.

- Observation: `personal_fil` is dead. The documents feature was removed (commit `13d26ad`, ADR-001 "Cleanup Decisions"), and a web test asserts the routes are gone. The table and its `volunteer_documents` alias remain defined.

- Observation: The Python alias layer translates table names but not columns. Every query still reads Norwegian columns and re-labels per query, e.g. `volunteer_cards.c.kortnummer.label("primary_text")` in `app/domain/volunteers/repository.py`.

- Observation: Alembic has no baseline. The chain starts at `20260313_1015_initial_auth_support.py`, which assumes the copied legacy schema already exists. The SQLAlchemy table definitions only declare the columns the app uses, so production tables almost certainly carry additional legacy columns not visible anywhere in this repository.

- Observation: There is no CI. `.github/workflows/` does not exist. `sonar-project.properties` exists, but nothing runs tests, `openapi-check`, or migrations on push. `ruff` is already a dev dependency in `pyproject.toml` but has no config and no enforcement.

- Observation: The deprecated mobile API is still served. `app/api/legacy/mobile_card.py` adapts two `/api/DigitalInternkort/*` endpoints onto the mobile-card service. The legacy backend it mirrored was declared archive-safe on 2026-05-05, but no measurement proves installed app versions have stopped calling the old paths.

- Observation: `frontend-eventside` is the only client that touches the database by table name (supabase-js string queries), and only the event tables. Those are already English and not renamed by this plan. The other clients speak only HTTP to this app.

- Observation: Type-level defects in otherwise-new tables: `events.updated_at` is nullable `DateTime` without timezone; `grupper.id_overgruppe` and `registrering_gruppe_medlem.droppet_av_user_id` lack foreign keys; `historie_kurs.gjennomfort_dato` is an `Integer` semester code misleadingly named "dato".

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

- Decision: The April mobile-card feature is kept; bringing `frontend-eventside` event writes through this backend stays out of scope for the numbered milestones (see Deferred Work).
  Date/Author: 2026-06-10 / Claude

- Decision: Extra production columns discovered by the M0 audit that no code reads are dropped in M3, each with its own Decision Log line naming the column and the evidence.
  Date/Author: 2026-06-10 / Claude

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

- Decision: Database access uses a request-scoped unit of work: one `AsyncSession` per HTTP request, injected via FastAPI dependency; repositories receive the session and never create their own; the dependency commits on success and rolls back on exception. `execute_in_transaction` and the session-per-method helpers are deleted.
  Rationale: Under `NullPool` on Vercel, session-per-call means connection-per-call against a remote pooler. A request-scoped session makes multi-step writes atomic by default (M7's atomic group approval depends on it) and pulls transaction mechanics out of services.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: Repositories return typed rows (Pydantic models validated at the repository boundary, or frozen dataclasses for internal read models), not `dict[str, Any]`. The mapper layer is deleted except where real derivation happens. Workflow protocols replace every `Any` with the real model type.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: The volunteer application lifecycle is encoded as a pure, exhaustively tested state machine in one module; the database enforces the state vocabulary with check constraints. State remains a column; there is no event sourcing and no workflow engine.
  Date/Author: 2026-06-10 / Claude (revision 2)

- Decision: The backend stays on FastAPI/Python. Alternatives considered: Django (the honest counterpoint — much of this codebase is hand-rolled Django: CSRF, sessions, admin UI; but those parts are now built, tested, and reviewed, so their marginal cost is near zero, while a rewrite costs a year of total team capacity and re-rolls the dice on every non-framework-shaped problem), .NET (died here once for organizational reasons that haven't changed; doesn't run on Vercel, so it would force a host migration too), TypeScript unification (the only alternative with a real argument — every sibling repo is TS — but it's an argument for the *forced-rewrite* scenario, which this is not). Corollary adopted as a standing rule: stop hand-rolling framework parts going forward; take maintained middleware/libraries off the shelf (M8's security headers are the first application).
  Date/Author: 2026-06-10 / Claude (revision 3)

- Decision: Supabase stays, used narrowly as managed Postgres + PITR + development branches + one storage bucket. Alternatives considered and rejected: Firebase (wrong shape for a relational domain; total query lock-in), Convex (TS-first, young vendor — wrong longevity risk profile for a system that outlives its builders), direct managed Postgres (loses branches/PITR/dashboard for no gain), SQLite (no persistent disk on Vercel; loses pg_trgm and JSON-aggregate features in active use). Standing target: this application becomes the only database client (see Deferred Work for the `frontend-eventside` migration), after which RLS is deny-all defense-in-depth.
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

- Decision: Security hardening (M8) is a standalone milestone whose items are independent of the structural milestones and may ship in any order, immediately.
  Rationale: Plaintext codes and decorative rate limiting are production exposure now; they must not queue behind a schema rename.
  Date/Author: 2026-06-10 / Claude (revision 3)

- Decision: Architectural tripwires — the conditions under which the modular-monolith decision is re-evaluated, recorded so the future team re-decides on evidence: (1) a component needs a different runtime shape (long-lived connections, heavy background workers, independently scaling traffic); (2) the team grows into multiple groups blocking each other's deploys; (3) a module needs a different language for a real reason. Separately, the codebase-split rule for future services: shares tables or auth with personnel → module in this repo; shares nothing → free to be its own small codebase (the future Sanity events API is the standing candidate; both answers are cheap there precisely because nothing entangles).
  Date/Author: 2026-06-10 / Claude (revision 3)

## Outcomes & Retrospective

To be written as milestones complete.

## Context and Orientation

The working directory is the repository root of `kvarteret-personal`. It is a FastAPI modular monolith: HTTP routes in `app/web/routes/{feature}/` (server-rendered HTMX admin UI) and `app/api/v1/` (JSON), domain logic in `app/domain/{feature}/`, SQLAlchemy Core table objects in `app/db/table_defs/`, the object graph wired in `app/runtime.py` with FastAPI `Depends()` factories in `app/dependencies.py`. Alembic migrations live in `migrations/versions/` named `YYYYMMDD_HHMM_description.py`. The production database is Supabase Postgres; the app deploys to Vercel from `api/index.py`. The checked-in `openapi.json` is the API contract sibling repos generate clients from (`make openapi` / `make openapi-check`). ADR-001 (`docs/adr/001-modular-monolith-event-bus.md`) fixes the architectural style: pragmatic modular monolith, explicit workflow coordinators for stateful processes, no distributed infrastructure. M9 adds ADR-002 (auth consolidation); M7 adds ADR-003 (domain-event audit log and the deferred outbox direction).

Terms of art:

- "Alias layer": the block of assignments at the bottom of `app/db/table_defs/__init__.py` giving Norwegian-named `Table` objects English Python names. Table names only; columns stay Norwegian.
- "Baseline migration": an Alembic revision recording the complete pre-existing schema as the start of the chain. Does not exist today.
- "Supabase development branch": Supabase's database branching feature cloning production schema into a disposable instance. Every destructive migration is rehearsed on a branch first.
- "Unit of work": one database session whose lifetime equals one HTTP request, created by a FastAPI dependency, shared by every repository the request touches, committed once at the end.
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
    events                  owns events, event_types, event_organizer_groups,
                                 event_organizer_group_memberships, rooms
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

Tables dropped outright (M2): `aspnetusers`, `aspnetroles`, `aspnetuserroles`, `grupper_admin_kobling`, `personal_fil`. Dropped in M4 after the bridge audit: `auth_migration_events` and `user_accounts.legacy_user_id`. Removed in M9: all volunteer rows in `auth.users`, then all admin rows once in-house passwords are cut over. Untouched: the event tables (except the `events.updated_at` type fix), `web_sessions`, `integration_tokens`, `mobile_card_april_state`.

## Plan of Work

### M0 — Schema baseline and drift audit

Capture the truth before changing it. Dump the full production schema (`pg_dump --schema-only` via the Supabase session pooler) and commit it under `docs/reference/schema-snapshots/<date>-pre-restructure.sql`. Inventory every table, column, index, constraint, RLS policy, trigger, view, and function in `public`, and diff three ways: against `app/db/table_defs/`, against the cumulative effect of `migrations/versions/`, and against the rename map above. Every production-only object gets a disposition (keep-and-define, rename, or drop) recorded in the Decision Log before M2 begins. The audit explicitly inventories two things later milestones depend on: every RLS policy and storage policy that references `auth.uid()` or the `authenticated` role (M9 must know what breaks when volunteer rows leave `auth.users`), and the policies on the event tables that `frontend-eventside` reads through the anon key (Deferred Work).

Create the baseline: a new first Alembic revision `<stamp>_baseline_legacy_schema.py` that creates the full pre-restructure schema, with `20260313_1015_initial_auth_support` re-parented onto it. Production is already at head, so the baseline is never executed there; its purpose is that `alembic upgrade head` on an empty Postgres reproduces production. Prove that against a local disposable Postgres. Verify Supabase point-in-time recovery is active (or take a manual data dump) so every later destructive step has a rollback path.

### M1 — CI pipeline and guardrails

Create `.github/workflows/ci.yml` running on every push and PR, plus a weekly `schedule:` trigger so a low-activity repo still catches rot between pushes: `uv sync`; `uv run pytest` (the suite needs no database); `make openapi-check`; a migration job that starts a `postgres:17` service container and runs `alembic upgrade head` from empty; `ruff check` (ruff is already a dev dependency — add its config to `pyproject.toml` and fix initial findings in a dedicated commit); and `pip-audit` (via `uv run pip-audit`) for known-vulnerable dependencies. Enable Dependabot (or Renovate) for pip and GitHub Actions so dependency updates arrive as small reviewable PRs rather than a crisis. Add `scripts/check_schema_drift.py`, which reflects `public` from a live database and diffs it against the app's table metadata; run it in CI against the migrated container and document in `docs/how-to/` how to run it against production. From M6 the workflow also runs `lint-imports`. Add `lint`, `lint-imports`, and `audit` targets to the `Makefile`.

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

Make ownership physical. Move each table's definition from `app/db/table_defs/public.py` into `app/domain/{owner}/tables.py` per the ownership map (all still bound to the one shared `MetaData` from `app/db/`, so Alembic and cross-module joins are unaffected). `app/db/table_defs/` retains only the shared metadata object and the `auth`/`storage` schema reflections. Fix the one ownership violation: migration `<stamp>_extract_mobile_card_access_codes.py` creates `mobile_card_access_codes` (`volunteer_id` PK/FK, `code_hash`, `created_at`), copies current values (hashing them if M8 has landed; otherwise as-is, with M8 finishing the job), and drops the two token columns from `volunteer_records`; `mobile_card/repository.py` now writes only its own tables.

Enforce the boundaries. Add `importlinter` config to `pyproject.toml` with three contract types: a layers contract (`web`/`api` may import `domain`; `domain` may import `db`/`infrastructure`/`shared`; nothing imports upward); an independence contract between domain modules' service/repository/workflow code; and explicit allowed read edges for read models — `{module}/queries.py` may import other modules' `tables.py` but never their services or repositories. Cross-module writes call the owning module's service: the one real case is application approval creating a volunteer, which becomes `VolunteerApplicationWorkflow` calling a `VolunteersService.create_from_application(...)` method instead of the applications repository inserting into `volunteer_records` directly. `lint-imports` joins CI (M1's workflow) and the Makefile.

Complete the module shape from ADR-001. Extract `app/domain/role_assignments/` (role-history queries, position management, semester-transfer preview/apply) out of `volunteers` — the ADR's listed follow-up. Split the two oversized modules along the read/write line: `volunteers` and `volunteer_applications` each get a `queries.py` holding list/search/detail read models (mirroring `groups/queries.py`), services keep writes. Wire through `app/dependencies.py` and `app/runtime.py`; move tests accordingly. Acceptance is structural: suite green, `lint-imports` green, no domain directory above ~1,200 lines, no single module above ~800.

### M7 — The volunteer application state machine and the domain-event audit log

The most important business process becomes readable from one file, fulfilling ADR-001's stated intent literally.

Create `app/domain/volunteer_applications/state_machine.py`, pure and I/O-free: `ApplicationState(StrEnum)` (`PROSPECT`, `INVITED`, `SUBMITTED`, `PROMOTED`, `REJECTED`), `MembershipState(StrEnum)` (`ACTIVE`, `DROPPED`), `ApplicationAction(StrEnum)` (`SUBMIT_PROFILE`, `RESEND_INVITATION`, `MARK_TRIAL_SHIFT`, `APPROVE`, `REJECT`, `DELETE`, `DROP_MEMBER`), an explicit transition table `TRANSITIONS: dict[tuple[ApplicationState, ApplicationAction], ApplicationState]`, and a `transition(state, action, *, context) -> TransitionResult` function that returns the new state, the named side effects to fire, and the domain-event record to append — or raises `IllegalTransition`. Guards encode the rules that depend on more than the state — the central one from the group-registration ADR: `APPROVE` on an application whose group membership is `ACTIVE` and whose group has other active members is illegal as a per-person action and legal only as the group-level action. The module docstring carries the state diagram; a test parametrizes the full state × action matrix so every cell is either asserted legal with its expected result or asserted to raise.

Side effects become data. `TransitionResult.effects` is a tuple of frozen, serializable effect records (e.g. `SendApplicantEmail(template=..., registration_id=...)`) that the workflow executes inline today, exactly as before — but because effects are named values chosen by the coordinator rather than method calls buried in service code, the deferred transactional outbox (see Deferred Work) becomes a localized change to *delivery*, not a redesign of *deciding*. No event bus, no subscribers: the coordinator remains the single place that says what happens.

The audit log. Migration `<stamp>_create_domain_events.py` adds the append-only `domain_events` table (`id`, `event_type`, `actor_user_account_id` nullable, `subject_type`, `subject_id`, `payload jsonb`, `occurred_at timestamptz`). The workflow inserts the event row returned by `transition()` in the same request transaction as the state change (M5's unit of work makes this one transaction by construction). This extends the domain's existing history-as-truth pattern (`role_assignments`) to the application lifecycle; state in columns remains the source of truth, and there is no replay or projection machinery. Record the decision and the deliberately-not-event-sourcing rationale as `docs/adr/003-domain-event-log.md`.

Re-wire the flow. `workflow.py` methods become: load typed record (M5) → `state_machine.transition(...)` → persist new state + insert domain event via repositories → execute the named effects — all inside the request transaction, which is what finally makes group approval atomic and all-or-nothing: one transaction promotes every active member or none. Replace the 14+ scattered status string literals in `repository.py` and `service.py` with the enums; the greppable invariant is that `"submitted"`-style literals appear in exactly one file. Implement the remaining ADR hardening: per-person approve hidden/blocked for active grouped applications (route + template + workflow guard), `Godkjenn alle` renamed to `Godkjenn gruppen`, the admin application list grouped by `group_id`, and tests for grouped approval, partial historical states, dropped members, and direct route access to blocked actions.

Constrain the database. Migration `<stamp>_application_state_constraints.py` adds `CHECK (status IN ('prospect','invited','submitted','promoted','rejected'))` on `volunteer_application_invites` (after an audit query confirms no other value exists in production — if one does, it is mapped and recorded in the Decision Log) and tightens transition-evidence columns where the audit allows (e.g. `promoted_at NOT NULL` when `status = 'promoted'` via a check constraint).

### M8 — Security hardening

Items in this milestone are independent of M2–M7 and of each other; ship them as they're ready, earliest first. Each lands with a test.

Security headers, off the shelf. Add a headers middleware (configure `starlette` middleware or a maintained package such as `secure` — per the standing rule, do not hand-roll): `Strict-Transport-Security` (production only), `X-Content-Type-Options: nosniff` globally (superseding the per-route media headers), `X-Frame-Options: DENY` / CSP `frame-ancestors 'none'`, `Referrer-Policy: strict-origin-when-cross-origin`, and a Content-Security-Policy for the admin UI (the HTMX templates are self-hosted; start with `default-src 'self'` plus the documented inline allowances the templates actually need, tightening as template cleanup allows).

Database-backed rate limiting. Replace the in-process `TTLCache` counters in `MobileCardService` with a small `rate_limits` table (key, window_start, count) using atomic `INSERT ... ON CONFLICT ... DO UPDATE` increments, behind the same interface so the service logic (including the existing TOCTOU-safe increment-before-validate order) is unchanged. Apply the same mechanism to the three other abuse surfaces: admin login (per-account and per-IP throttle with lockout backoff — currently unthrottled), the public prospect endpoint, and access-code requests (currently the per-IP/email window). On Vercel, in-process counters are per-instance and reset on recycle; Postgres is the only shared state this app has, and at this traffic the extra query is irrelevant.

Hashed access codes. Store only a salted hash of mobile-card access codes (the 6-character codes are low-entropy, so use a slow hash or HMAC with a server key, not bare sha256); compare in constant time. Coordinate with M6: the new `mobile_card_access_codes.code_hash` column is the natural landing spot, but if M8 ships first, hash in place in the legacy columns. Audit the mobile session token mechanism at the same time: confirm whether bearer session tokens are server-side rows (revocable) or stateless; if stateless, move them to rows so a stolen phone or departed volunteer can be cut off, aligning with the session model the admin UI already uses.

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
- `frontend-eventside` stops querying the database directly. Today it reads event tables via supabase-js with the anon key, which makes RLS policies on those tables production authorization code maintained outside any review process. The planned central events API (possibly fronting Sanity so all clients share one representation) retires the pattern naturally; afterward, set deny-all RLS on `public` as defense-in-depth. Until then, the M0 policy inventory is the review of record for those policies.
- The Sanity events API itself, when it materializes, is the standing candidate for the codebase-split rule (Decision Log): it shares no tables and no auth with personnel, so module-in-this-repo and own-small-codebase are both legitimate; decide then, cheaply.
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
    grep -rn "TTLCache" app/domain/mobile_card/   # acceptance: no rate-limit usage remains
    psql "$DATABASE_URL" -c "select internkortaccesstoken from personal limit 3"
    # acceptance after hashing (pre-M3 names shown): no plaintext 6-char codes

Auth invariants (M8/M9):

    uv run pytest tests -k "gotrue_user_without_account or permission_matrix or login_lockout" -q

Full verification battery after each milestone:

    make test

## Validation and Acceptance

M0: the schema snapshot is committed, every production-only object has a Decision Log disposition, the `auth.uid()`/storage-policy inventory exists, and `alembic upgrade head` on empty Postgres produces a schema structurally identical to the snapshot.

M1: a PR that breaks a test, stales `openapi.json`, fails ruff, fails pip-audit, or breaks the migration chain fails CI visibly on GitHub; the weekly scheduled run appears in the Actions history; Dependabot opens its first PRs; `scripts/check_schema_drift.py` exits zero against the CI-migrated container.

M2: production no longer lists `aspnetusers`, `aspnetroles`, `aspnetuserroles`, `grupper_admin_kobling`, or `personal_fil`; the private archive export exists; `make test` passes with the definitions removed.

M3: production contains only English names from the rename map; login, volunteer detail, and `POST /api/v1/mobile-card/sessions` work; `make openapi-check` is clean; `grep -rn "fornavn\|etternavn\|kortnummer\|grupper\b" app/` matches nothing outside migrations.

M4: Vercel logs show four weeks of zero non-synthetic `legacy.digital_internkort.hit` events before removal; the DigitalInternkort routes 404 in production afterward; `openapi.json` no longer mentions them; `user_accounts` has no `legacy_user_id`.

M5: `grep -rn "session_factory()" app/domain app/auth` matches nothing (sessions enter only through the request dependency or `session_scope()`); `grep -rn "dict\[str, Any\]" app/domain/*/repository.py` matches nothing; `app/domain/volunteers/mappers.py` is deleted; a contract test per module passes against fake and real repositories in CI; one warm admin page that previously issued N connections issues 1 (assert via the new engine event listener's log output in a local timing run, recorded in `Artifacts and Notes`).

M6: every table definition lives in its owning module's `tables.py`; `make lint-imports` passes and CI fails on a deliberately introduced cross-module service import (verify once, then revert); `mobile_card_access_codes` exists and `volunteer_records` has no token columns; `app/domain/role_assignments/` exists; no domain directory exceeds ~1,200 lines (`find app/domain/* -name '*.py' | xargs wc -l`).

M7: the state × action matrix test covers every combination; the status-literal grep returns no output; per-person approval of an active grouped member is rejected by the workflow and absent from the template; group approval promotes all active members in one transaction (test: induce a failure on the second member and assert the first is not promoted); every transition in a test run inserts exactly one `domain_events` row in the same transaction (test: induce a post-insert failure and assert neither the state change nor the event row persisted); the check constraint exists in production and an `UPDATE ... SET status='bogus'` is rejected; `docs/adr/003-domain-event-log.md` exists.

M8: the header curl shows all five headers in production; `TTLCache` no longer backs any rate limit and two concurrent simulated instances share one limit (test against the CI Postgres container); admin login locks out after the configured failures and logs the event; access codes at rest are hashes and session creation still works end-to-end; the prospect endpoint's `409` bodies carry no internal ids and the regenerated sibling client compiles; the GoTrue-user-without-account regression test passes.

M9: every admin route is guarded by `require_permission` (grep: no remaining ad-hoc `role ==` checks in `app/web/routes/`); the before/after permission-matrix test passes; all admins have logged in via argon2 verification and the GoTrue gateway code is deleted; `auth.users` is empty; `docs/adr/002-auth-consolidation.md` exists; the `SmsGateway` protocol exists with the email-code flow still the shipped credential.

## Idempotence and Recovery

Every migration is rehearsed on a Supabase development branch before production, and production is touched only with a verified PITR window or manual dump. M2 and M4 drops are preceded by archival exports; recovery is restoring the export. The M3 rename migration is symmetric (`downgrade()` renames back exactly); recovery inside the window is `alembic downgrade -1` plus the still-live previous deployment. The M6 token-table migration copies before dropping, so its downgrade re-creates the columns and copies back. The M7 check constraints are preceded by audit queries and are droppable independently; `domain_events` is additive. M8 items are individually revertible (middleware removal, table-backed limiter behind the existing interface, re-issue of access codes if hashing migration must roll back — codes are short-lived by design). M9 keeps the GoTrue login path behind a setting until the argon2 path is proven, exports `auth.users` before any deletion, and migrates permissions with a before/after matrix test, so each cutover has a rollback that is configuration, not surgery. M5–M7 code changes are behavior-preserving refactors shipped behind the full suite, the contract tests, and (from M6) the import linter; each milestone ends with code and schema agreeing, so the plan can pause indefinitely at any milestone boundary.

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
    CI: none (.github/workflows absent); Sonar config present; ruff installed, unconfigured
    security posture: rate limits in-process (TTLCache), access codes plaintext,
                      no security headers, prospect 409s leak internal ids,
                      admin login unthrottled; sessions/CSRF/cookies sound
    auth stores: admins and all volunteers mixed in auth.users; admin login
                 gated on user_accounts rows (code-level invariant, untested)

## Interfaces and Dependencies

Tooling additions: `import-linter`, `pip-audit`, `argon2-cffi` (M9), a maintained security-headers middleware (M8), `apgdiff` or an equivalent schema-diff approach, GitHub Actions with a `postgres:17` service container, Dependabot. `ruff` is already present. No new runtime infrastructure — no ORM adoption, no workflow engine, no queue, no identity vendor.

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

Revision note (revision 3, 2026-06-10): Folded in the security review (new M8: database-backed rate limiting, hashed access codes, security headers, enumeration fixes, auth-invariant regression test — items shippable immediately and independent of M2–M7), the auth consolidation (new M9: in-application permission layer with scoped grants, in-house argon2 admin passwords, volunteers removed from `auth.users`, GoTrue retired, `SmsGateway` port defined), and the audit/durability direction from the CQRS and event-driven re-examination (M7 extended with the `domain_events` transactional audit log and side-effects-as-data; transactional outbox recorded as a deferred decision — direction fixed, contents and dispatcher deliberately not designed now, since scheduled jobs are not being added this quarter). Platform decisions recorded with alternatives (stay FastAPI, Supabase narrowed to managed Postgres + storage, no identity vendor, architecture tripwires and the codebase-split rule). M1 extended with weekly scheduled CI, pip-audit, and Dependabot for durable upkeep; M0 extended with the `auth.uid()`/storage-policy inventory M9 depends on; new Deferred Work section carries the next-quarter items (jobs, outbox, `frontend-eventside` API migration, Sanity events API split decision, SMS provider selection).
