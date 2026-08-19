# Legacy restructure: completed work and deferred follow-ups

This document is a historical retrospective of the legacy restructure merged in June 2026. It is not the current architecture entry point. Read `README.md` and `docs/README.md` for current behavior, and use git history when the original milestone-by-milestone execution transcript is needed.

The work was planned and executed under the repository-level `PLANS.md` guidance. This shorter record preserves the intent, outcome, important decisions, and remaining work without retaining machine-specific paths or superseded implementation instructions.

## Purpose / Big Picture

The restructure removed unused .NET-era schema and APIs, made the database and Python code easier to navigate, introduced explicit domain boundaries, made volunteer-application transitions auditable, and hardened public and authentication-related surfaces.

The user-visible application remained a FastAPI service with a server-rendered admin UI and mobile-card API. The main benefit was operational: contributors gained a reproducible local stack, a checked schema baseline, clearer ownership, safer transactions, and tests that detect architectural drift.

## Progress

- [x] (2026-06-10) M0 recorded the pre-restructure schema and identified every retained, renamed, archived, and removed object.
- [x] (2026-06-10) M1 added CI and guardrails for tests, linting, import boundaries, OpenAPI drift, schema drift, and dependency auditing.
- [x] (2026-06-10) M2 privately archived required historical rows and removed unused legacy identity, event, file, and signup structures.
- [x] (2026-06-10) M3 renamed the active personnel schema to English and corrected selected column types and foreign keys.
- [x] (2026-06-10) M4 removed the deprecated `/api/DigitalInternkort/*` compatibility API and the remaining authentication-bridge vestiges.
- [x] (2026-06-13) M5 established request-scoped SQLAlchemy sessions and commit-before-side-effect behavior.
- [x] (2026-06-13) M6 split the application into enforceable domain modules with explicit dependency seams.
- [x] (2026-06-13) M7 made the volunteer-application lifecycle an explicit state machine and wrote domain events in the same database transaction as state changes.
- [x] (2026-06-13) M8 added rate limiting, keyed access-code hashing, security headers, enumeration-resistant responses, and regression coverage for the admin-login invariant.
- [ ] M9 remains a separate auth-consolidation project. Permission and SMS interfaces exist as design scaffolding, but route adoption, role-grant persistence, in-house admin passwords, and GoTrue retirement were not part of the merged restructure.

## Surprises & Discoveries

- Observation: Generated clients and sibling source can outlive the API they once described.
  Evidence: the event API and tables were retired in this repository, while stale generated operations remained elsewhere. Current public event pages and feeds in `samfunnetibergen` read from Sanity; see `docs/reference/api-boundaries.md`.

- Observation: Request-scoped transactions were necessary before repository boundaries could be made honest.
  Evidence: `app/main.py` installs the request-session middleware, and write services use the shared request session so database state commits before email or storage effects run.

- Observation: The permission model designed for M9 could be merged safely only as unused scaffolding.
  Evidence: `app/auth/permissions.py` and `app/infrastructure/sms/protocols.py` exist, but the current schema has no `role_grants` migration and admin password verification still uses Supabase Auth.

- Observation: Mobile-card sessions remained signed, stateless tokens after the restructure.
  Evidence: `app/domain/mobile_card/sessions.py` signs and verifies token payloads without a server-side revocation table. Per-device revocation remains separate work.

## Decision Log

- Decision: Treat FastAPI routes and Pydantic models as the API source of truth and keep `openapi.json` generated from them.
  Rationale: A checked contract lets sibling consumers detect API changes without making a generated client the owner of retired behavior.
  Date/Author: 2026-06-10 / project team

- Decision: Retire the personal event API and its tables.
  Rationale: Current event delivery moved to Sanity-backed consumers. Stale generated client operations are historical artifacts, not a reason to preserve an unused service boundary.
  Date/Author: 2026-06-10 / product decision

- Decision: Use one SQLAlchemy session per request and commit state before invoking external effects.
  Rationale: Services crossing several repositories need one transaction so partial approval or lifecycle changes cannot escape as durable state.
  Date/Author: 2026-06-10 / project team

- Decision: Enforce a modular monolith before considering multiple deployable services.
  Rationale: Import contracts and table ownership provide most of the organizational benefit without adding network calls, distributed transactions, or deployment overhead.
  Date/Author: 2026-06-10 / project team

- Decision: Hash six-digit mobile access codes with HMAC-SHA256 using the application secret.
  Rationale: A bare digest of a six-digit value is trivial to brute-force after a database leak. A keyed digest prevents offline verification when the key is stored outside the database.
  Date/Author: 2026-06-10 / project team

- Decision: Defer auth consolidation to a dedicated, production-coordinated change.
  Rationale: Adding role grants, changing every authorization check, cutting over admin password verification, and deleting identity-provider rows require rollout and rollback controls beyond a code-structure change.
  Date/Author: 2026-06-11 / product decision

## Outcomes & Retrospective

The restructure merged through pull request #21. The resulting source has a reproducible Postgres development harness, linear Alembic history, checked OpenAPI and schema drift, request-scoped transactions, domain-oriented repositories, import-linter contracts, an explicit volunteer-application state machine, transactional domain events, database-backed rate limiting, hashed access codes, and security headers.

Later work built on this foundation. Durable volunteer email delivery shipped in August 2026, and friend invitations replaced the temporary group-application model. Those changes are described in `plans/durable-email-and-posthog-observability.md` and `plans/individual-friend-invitation-applications.md` and should not be reconstructed from this older plan.

Auth consolidation was deliberately not completed. `docs/adr/002-auth-consolidation.md` records the accepted direction, but current runtime behavior and configuration docs remain authoritative for what is actually deployed.

## Context and Orientation

The current application factory is `app/main.py:create_app`. Runtime dependency construction lives in `app/runtime.py`. `app/db/tables.py` aggregates SQLAlchemy metadata, while each domain owns its table definitions under `app/domain/<domain>/tables.py` or an infrastructure-specific table module.

The main domain modules created or clarified by this work are:

- `app/domain/volunteers/` for volunteer records and searches.
- `app/domain/role_assignments/` for positions and semester transfer.
- `app/domain/volunteer_applications/` for application state, transitions, audit events, and friend-invitation relationships.
- `app/domain/mobile_card/` for access codes and mobile-card session payloads.
- `app/domain/admin_accounts/` for application-side administrator records.

The pre-restructure schema inventory remains in `docs/reference/schema-snapshots/20260610-pre-restructure-inventory.md`. Historical data required before destructive migrations was exported to a restricted operator-controlled archive outside the repository. The public plan intentionally does not record its machine-specific location.

## Completed Milestones

M0 and M1 established evidence and guardrails. `scripts/check_schema_drift.py`, the checked OpenAPI artifact, CI, Ruff, import-linter, and dependency auditing made later removal work observable.

M2 through M4 removed the dead .NET-era surface. The relevant Alembic revisions are `20260610_1000_drop_retired_event_tables.py`, `20260610_1100_rename_schema_to_english.py`, `20260610_1200_fix_column_types_and_fks.py`, and `20260610_1300_drop_auth_bridge_vestiges.py`. Deprecated DigitalInternkort routing was removed from the FastAPI router rather than kept for stale consumers.

M5 and M6 changed the internal structure. Repositories share the request session; domains communicate through explicit models and protocols; `app/db/tables.py` aggregates metadata without becoming a shared business-logic module; import-linter prevents forbidden cross-domain dependencies.

M7 and M8 changed runtime guarantees. `app/domain/volunteer_applications/state_machine.py` owns legal state transitions, repository writes append `domain_events` transactionally, `app/domain/mobile_card/` uses keyed access-code hashes, and the `rate_limits` table backs throttling for sensitive endpoints.

M9 stopped at architecture and interfaces. Do not describe `role_grants`, universal `require_permission` adoption, Argon2 admin passwords, removal of volunteers from `auth.users`, or GoTrue retirement as implemented until current source and migrations prove each state independently.

## Validation and Acceptance

The historical merge was accepted after the unit/web suite, Postgres lifecycle tests, Ruff, import-linter, OpenAPI drift, schema drift, and dependency audit passed. Counts recorded in the original plan belong to that June 2026 commit and should not be presented as current totals.

For current validation, use the repository commands rather than copying the historical Docker transcript:

    kv test
    kv lint
    kv audit
    kv openapi --check

Use `docs/how-to/run-tests.md` and `docs/how-to/local-development.md` for the current Postgres and end-to-end workflow.

## Idempotence and Recovery

The completed migrations are part of the linear Alembic history and must not be manually replayed against an already-migrated database. Build disposable databases from the current migration head for verification. Restore historical data only through the restricted archive and an approved operator procedure; never copy archived rows, credentials, hashes, or personal data into this repository.

## Interfaces and Dependencies

FastAPI routes and Pydantic models remain the API source of truth. Regenerate `openapi.json` after route, model, status-code, or operation-ID changes. Current sibling ownership and runtime consumption are documented in `docs/reference/api-boundaries.md`; do not infer them from June 2026 generated clients or this retrospective.

Supabase remains a runtime dependency for managed Postgres, Auth, and storage in the current source. Vercel runs the FastAPI application. The adjacent `samfunnetibergen` checkout proxies volunteer prospects to this service but reads public events from Sanity. The React Native mobile app calls current mobile-card and now-playing routes; generated personal event operations are retired.

Revision note (2026-08-14): Replaced the 909-line living implementation transcript with a concise historical retrospective. Removed personal attribution and machine-specific archive paths, reconciled superseded M9 decisions, and verified retained current-boundary statements against source and sibling checkouts.
