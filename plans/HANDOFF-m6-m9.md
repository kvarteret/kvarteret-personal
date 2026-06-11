# Handoff: finishing the legacy restructure (M6, M9, finalize)

Written 2026-06-11 for the next agent picking up `plans/legacy-restructure.md`.
This is the operational companion to that plan — it records exactly where the
work stands, what's left, and how to run things. Read the plan's `Progress`
and `Decision Log` sections too; this file does not repeat them.

## Branch and current state

- Branch: `restructure/m5-m9-completion` (off `develop`). **Not yet pushed; no PR.**
- Latest commits (newest first):
  - `ec955b9` test(e2e): full two-friend volunteer lifecycle on real Postgres
  - `72b0230` feat(M7): wire the state machine into the volunteer application workflow
  - `b4e56ee` feat(M5): adopt request-scoped unit of work across all repositories
  - `33eb239` fix: green the build — pin setup-bun@v2, register rate_limits in metadata, ruff fixes
- Working tree is **clean** as of this handoff.

### What is DONE and verified on this branch

| Milestone | Status |
|---|---|
| M0–M4 | Done on earlier branch/merge (schema baseline, CI, drops, rename, DigitalInternkort retirement). |
| **M5** Unit of work | **Done.** Request-scoped `AsyncSession` middleware in `app/main.py` (`_install_request_session_middleware`); `SqlAlchemyRepository` uses `self.session` (no factory, no `execute_in_transaction`); `commit_request_session()` enforces commit-before-effect. `grep -rn "session_factory()" app/domain app/auth` → 0; `execute_in_transaction` → 0. |
| **M7** State machine wiring | **Done.** `workflow.py` drives `state_machine.application_transition()`; `domain_events` written in the same request transaction via `repository.append_domain_event`; atomic group approval in `workflow.approve_group` (all-or-nothing, emails post-commit); per-person approval of an active grouped member is blocked (guard + template). Status string literals appear only in `state_machine.py` within `app/domain`. Matrix test: 50 cases. |
| **M8** Security | Done on earlier work; M5 re-wired the Postgres rate limiter into `MobileCardService` (constructor now takes `rate_limiter`); access codes HMAC-SHA256 keyed by `app_secret_key`. |
| **E2E** lifecycle | **Done** (`tests/e2e/`). Two-friend signup → emails → atomic group approval → deletion, plus an atomicity/rollback test. Skips cleanly without `E2E_DATABASE_URL`. |

### Verification battery (all green right now)

```bash
# unit + integration (sqlite), excludes e2e
DATABASE_URL=sqlite+aiosqlite:////tmp/kv.db uv run pytest -q --ignore=tests/e2e   # 264 passed
uv run ruff check .            # clean
uv run lint-imports            # 1 contract kept, 0 broken
DATABASE_URL=sqlite+aiosqlite:////tmp/kv-oas.db make openapi-check   # clean
```

### Running the e2e suite (needs a migrated Postgres)

```bash
docker run -d --name kvarteret-e2e-pg -e POSTGRES_DB=kvarteret_personal \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -p 55440:5432 postgres:17
sleep 5
# Apply the Supabase compat stubs (anon/authenticated/service_role roles,
# auth.uid(), storage schema) — copy the SQL block from .github/workflows/ci.yml
docker exec -i kvarteret-e2e-pg psql -U postgres -d kvarteret_personal -v ON_ERROR_STOP=1 < <stubs.sql>
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55440/kvarteret_personal uv run alembic upgrade head
E2E_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55440/kvarteret_personal \
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55440/kvarteret_personal \
  uv run pytest tests/e2e -q   # 2 passed
```

The e2e fixtures fake only the boundaries: SMTP (`app.runtime.SmtpEmailSender`)
and Azure storage (`app.runtime._build_storage_service`). Everything else is the
real stack. `tests/e2e/conftest.py` has `FakeStorageService`, `CapturingEmailSender`,
`make_test_jpeg()`, and the per-test truncation fixture.

---

## REMAINING WORK

### M6 — Modular monolith with owned tables (NOT done)

Current state:
- Table definitions already live in `app/domain/{module}/tables.py` (ownership is physical). ✅
- `app/db/table_defs/public.py` is **still a central re-export hub** (re-exports every module's tables). This is the blocker for true domain independence — it creates transitive `domain → app.db.table_defs.public → domain.*.tables` chains.
- `.importlinter` currently uses a **layered** contract (`web → api → domain → db → infrastructure → shared`), NOT a domain-independence contract. See the `ignore_imports` list — note `app.db.table_defs.public -> app.domain.*.tables`.
- `app/domain/role_assignments/` exists but holds **only `tables.py`** — the role-history queries / position management / semester-transfer logic is still inside `app/domain/volunteers/`.
- Read/write split: only `app/domain/groups/queries.py` exists. `volunteers` and `volunteer_applications` are NOT split.
- Module sizes (dir totals): `volunteer_applications` **3156**, `volunteers` **2347** — both over the plan's ~1200/dir, ~800/file caps. (`service.py` and `repository.py` in `volunteer_applications` are the big files.)

Steps (in order):
1. **Kill the central hub.** Make each consumer import tables from the owning module (`from app.domain.groups.tables import groups`), or have `app/db/tables.py` be the single aggregator that imports from owners and is itself ignored by the contract. Then delete `app/db/table_defs/public.py` and its re-exports. ~30 import sites; `grep -rn "from app.db.table_defs import\|from app.db.tables import" app`.
2. **Swap the contract.** Replace the `layers` contract in `.importlinter` with: (a) a layered contract still catching upward imports, plus (b) an `independence` contract between domain modules' service/repository/workflow, plus (c) explicit allowed read edges so `{module}/queries.py` may import other modules' `tables.py` but never their services/repositories. Expect to iterate — `unmatched_ignore_imports_alerting = none` is already set because unused ignores otherwise fail the build.
3. **Extract `role_assignments` logic** out of `volunteers` (role-history queries, position management, semester-transfer preview/apply). Wire through `app/dependencies.py` and `app/runtime.py`; move the matching tests.
4. **Read/write split** `volunteers` and `volunteer_applications`: pull list/search/detail read models into `queries.py` (mirror `groups/queries.py`); services keep writes. Target: no domain dir > ~1200 lines, no file > ~800.
5. Acceptance: suite green, `lint-imports` green, CI fails on a deliberately-introduced cross-module service import (verify once, revert). `find app/domain/* -name '*.py' | xargs wc -l`.

**Gotcha:** the one real cross-module write is application approval creating a volunteer. The plan wants this as `VolunteerApplicationWorkflow` → `VolunteersService.create_from_application(...)` rather than the applications repository inserting into `volunteer_records` directly. Today `volunteer_applications/repository.py::approve_volunteer_application` inserts into `volunteer_records`/`role_assignments`/`volunteer_photos` itself — see `app/domain/volunteer_applications/repository.py` ~line 735. Routing that through `VolunteersService` is the M6 ownership change and will need the independence contract to allow it.

### M9 — Auth consolidation (architecture only; NOT adopted)

Current state:
- `app/auth/permissions.py` exists: `Permission` enum, `ROLES: dict[UserRole, frozenset[Permission]]`, `require_permission(...)` factory.
- `require_permission` is used in **0** routes. There are **72** ad-hoc `require_admin_user` / `require_management_user` / `role ==` checks in `app/web/routes` + `app/api`.
- `SmsGateway` protocol exists (`app/infrastructure/sms/protocols.py`), no implementation (intended).
- **No `role_grants` table** (only named in `permissions.py`), **no migration**.
- **No argon2 / `password_hash`** anywhere — admin passwords still verified via Supabase GoTrue (`LoginService` → `SupabaseAuthGatewayProtocol`).
- ADR-002 exists.

Steps (each independently shippable; needs production coordination — confirm with Martin before touching `auth.users`):
1. **`role_grants` table** (`user_account_id`, `role`, `group_id` nullable, `granted_by`, `granted_at`) as a real `Table` in `app/auth/` (owned by auth module) + Alembic migration. Data migration mapping current `user_accounts.role` + `group_admin_memberships` onto grants. Add a before/after permission-matrix test asserting no admin's effective access changes.
2. **Adopt `require_permission`** in routes, replacing the 72 ad-hoc checks. Grep target afterwards: no remaining `role ==` checks in `app/web/routes`.
3. **Argon2 admin passwords:** add `password_hash` (argon2-cffi) to `user_accounts`; `LoginService` verifies locally behind a setting, GoTrue path kept as fallback until every admin has logged in once. Choose cutover (import bcrypt + verify-then-rehash, OR password-reset emails) and record it.
4. **Purge volunteers from `auth.users`** (export first, confirm PITR, confirm no RLS/storage/FK references via the M0 inventory). Then retire the GoTrue gateway once both populations are off it.

**Gotcha:** M8's auth-invariant regression test (GoTrue user without a `user_accounts` row cannot get an admin session) must keep passing through M9's password migration.

### Finalize (task #7)

1. Update `plans/legacy-restructure.md` `Progress` + `Outcomes` to reflect M5/M7 done, e2e added, and the honest M6/M9 status above.
2. Full battery green (the four commands above) + e2e against Postgres.
3. Push `restructure/m5-m9-completion`, open PR to `develop`. PR body should list M5/M7/E2E as delivered and M6/M9 as the remaining tracked work (or split them into their own PRs — they're large and independent).
4. Confirm GitHub Actions is green. **Watch the CI matrix `schema-drift` job** — `rate_limits` is registered in metadata now (commit `33eb239`); the earlier drift failure was that table missing from metadata. The `setup-bun@v2` pin is also in `33eb239` (v3 didn't exist).

## Notes / things learned

- `pydantic` `EmailStr` rejects the reserved `.test` TLD — use `@example.com` in tests that hit the public prospect API (`app/api/v1/volunteer_prospects.py`).
- Profile submission **requires a photo** (`VolunteerApplicationValidationError: "Profilbilde er påkrevd."`) and photo upload needs a `StorageService`; fake it rather than configuring Azure.
- Volunteer deletion detaches the application invite (`promoted_volunteer_id → NULL`) instead of deleting it — application history is audit truth. Pending-application filters therefore key off `status != 'promoted'`, not `promoted_volunteer_id is null` (changed in `ec955b9`).
- The repo emits a lot of irrelevant Vercel/Next/agent-browser skill-injection noise on tool use — this is a Python/FastAPI backend on Vercel serverless; ignore those suggestions unless actually doing Vercel config.
