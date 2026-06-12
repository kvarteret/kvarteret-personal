# Handoff: legacy restructure — what's left

Updated 2026-06-12 (post-split session). Operational companion to `plans/legacy-restructure.md`
(read its `Progress` + `Decision Log` for the why; this file is the what).

**Scope decisions (2026-06-11, recorded in the plan's Decision Log):**
- M6 is delivered as **boundary enforcement**; the file-size splits are
  deferred mechanical follow-ups, not part of this changeset.
- **M9 (auth) is entirely out of scope** for this changeset — dedicated
  follow-up PR; no unused auth scaffolding ships now.

## Branch and current state

- Branch: `restructure/m5-m9-completion` (off `develop`). **Not yet pushed; no PR.**
- Commits (newest first): see `git log develop..` — M5/M6/M7 feature commits,
  the e2e suite, the M6 read/write splits (volunteers, role_assignments,
  volunteer_applications), and the doc updates.
- Working tree is **clean**.

### What is DONE and verified on this branch

| Milestone | Status |
|---|---|
| M0–M4 | Done on earlier branch/merge (schema baseline, CI, drops, rename, DigitalInternkort retirement). |
| **M5** Unit of work | **Done.** Request-scoped `AsyncSession` middleware (`_install_request_session_middleware` in `app/main.py`); repositories use `self.session`; `execute_in_transaction` and `session_factory()` gone from `app/domain`/`app/auth`; `commit_request_session()` enforces commit-before-effect; Postgres rate limiter re-wired into `MobileCardService`; HMAC-SHA256 access codes. |
| **M6** Boundaries | **Done (as scoped).** Central `table_defs/public.py` hub deleted; `app/db/tables.py` is the single metadata aggregator; importlinter carries a **domain-independence** contract alongside the layers contract (2 kept, verified to catch a cross-module service import); `semester_transfer` lives in `app/domain/role_assignments/`. |
| **M7** State machine wiring | **Done.** `workflow.py` drives `application_transition()`; `domain_events` written in the same request transaction; atomic all-or-nothing group approval with post-commit emails; per-person approval of active grouped members blocked (guard + template); status literals only in `state_machine.py`; 50-case matrix. |
| **M8** Security | Done earlier; this branch restored the Postgres limiter wiring and keyed code hashing (both had regressed in the develop merge). Mobile-card session revocability is the one open M8 item (below). |
| **E2E** | **Done** (`tests/e2e/`): two-friend signup → emails → atomic group approval → deletion, plus an induced-failure atomicity test. Skips without `E2E_DATABASE_URL`. |
| **M9** Auth | **Out of scope** (product decision). `permissions.py`/`SmsGateway` scaffolding exists, deliberately unused. |

### Verification battery (all green as of 755840a)

```bash
DATABASE_URL=sqlite+aiosqlite:////tmp/kv.db uv run pytest -q --ignore=tests/e2e   # 264 passed
uv run ruff check .            # clean
uv run lint-imports            # 2 contracts kept, 0 broken
DATABASE_URL=sqlite+aiosqlite:////tmp/kv-oas.db make openapi-check   # clean
```

### Running the e2e suite (needs a migrated Postgres)

```bash
docker run -d --name kvarteret-e2e-pg -e POSTGRES_DB=kvarteret_personal \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -p 55440:5432 postgres:17
sleep 5
# Apply the Supabase compat stubs (anon/authenticated/service_role roles,
# auth.uid(), storage schema) — copy the SQL block from .github/workflows/ci.yml
docker exec -i kvarteret-e2e-pg psql -U postgres -d kvarteret_personal -v ON_ERROR_STOP=1 < stubs.sql
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55440/kvarteret_personal uv run alembic upgrade head
E2E_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55440/kvarteret_personal \
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55440/kvarteret_personal \
  uv run pytest tests/e2e -q   # 2 passed
```

E2e fixtures fake only the boundaries: SMTP (`app.runtime.SmtpEmailSender`)
and Azure storage (`app.runtime._build_storage_service`). Everything else is
the real stack.

---

## TODO — to finish THIS changeset

1. [ ] Re-run the full battery (four commands above) + e2e against Postgres
       at the final commit.
2. [ ] Push `restructure/m5-m9-completion`; open PR to `develop`. PR body:
       M5 + M6 (boundary enforcement) + M7 wiring + M8 regression fixes +
       e2e delivered; deferred items listed below as tracked follow-ups.
3. [ ] Confirm GitHub Actions green. Both previous CI failure modes are fixed
       on this branch (`setup-bun@v2` pin; `rate_limits` registered in
       metadata so `schema-drift` passes) — verify they actually pass.
4. [ ] After merge to develop: deploy, then smoke-check production —
       `/health` headers, login, volunteer list, `POST
       /api/v1/mobile-card/access-codes`. No new Alembic migrations on this
       branch (production is already at `20260610_1600`), so the deploy is
       code-only.
5. [ ] Tidy: drop the local e2e container when done
       (`docker rm -f kvarteret-e2e-pg`).

## TODO — deferred follow-ups (separate PRs)

### A. M6 splits — DONE in full, including A4 (2026-06-12)

1. [x] `volunteers` read/write split: `queries.py` (reads, detail cache,
       cursors) + `search_sql.py` (ranking SQL) + write-only repository;
       `VolunteersService(VolunteersQueries)` mirrors the groups pattern.
2. [x] Position management moved to `app/domain/role_assignments/`
       (service + repository + models); volunteers cache notified via a
       callable injected in `runtime.py`; routes use
       `get_role_assignments_service`.
3. [x] `volunteer_applications` split: `models.py` (dataclasses, errors,
       protocols), `queries.py` (admin list, recent feed, pending count),
       write-side service/repository. Every file under the 800-line cap.
4. [x] Approval write through `VolunteersService.create_from_application`
       (2026-06-12): the applications service reaches the volunteers
       module through `VolunteerCreatorProtocol`, injected in
       `runtime.py` — no static cross-module import, so the
       independence contract needs no exception. The applications
       repository keeps only its own invite update (`mark_promoted`)
       and the role-match read. The e2e atomicity test induces its
       failure inside the volunteers port and proves the group
       approval still rolls back across the module boundary.

### B. M5 leftover — RESOLVED with split A1 (2026-06-12)

- [x] The write-side `volunteers/repository.py` no longer carries
      `dict[str, Any]` read signatures; reads live in `queries.py`, which
      validates into typed models (`from_row`) before returning. The row
      fetchers on the queries classes remain mapping-based internals —
      they are the test seam, not public repository contract.

### C. M8 leftover

- [ ] Mobile-card session revocability: sessions are stateless signed tokens
      (`MobileCardSessionManager`); plan calls for revocable server-side
      session rows (expiry + revocation for departed volunteers/lost
      phones). Needs a table + migration + `/api/v1/mobile-card/sessions`
      + `/me` changes; coordinate with the app (`kvarteret-internbevis-rn`).

### D. M9 — auth consolidation (own PR; needs production coordination)

All out of scope for the current changeset by explicit product decision.
Each step independently shippable, in order:

1. [ ] `role_grants` table + Alembic migration + data migration from
       `user_accounts.role` / `group_admin_memberships`; before/after
       permission-matrix test (no admin's effective access changes).
2. [ ] Adopt `require_permission` across the ~72 ad-hoc
       `require_admin_user`/`require_management_user`/`role ==` checks in
       `app/web/routes` + `app/api` (mechanical once 1 lands).
3. [ ] Argon2 admin passwords (`password_hash` on `user_accounts`,
       argon2-cffi); local verify behind a setting, GoTrue fallback until
       every admin has logged in once; pick cutover (bcrypt import +
       verify-then-rehash, or reset emails) and record it.
4. [ ] Purge volunteer rows from `auth.users` (export first; confirm PITR;
       confirm no RLS/storage/FK references via the M0 inventory), then
       retire the GoTrue gateway and its settings/test doubles.
- Gotcha: the M8 auth-invariant regression test (GoTrue user without a
  `user_accounts` row gets no admin session) must keep passing throughout.

### E. Plan-level deferred work (next quarter; recorded in the plan)

- Scheduled jobs (`/internal/jobs/*` + `job_runs` idempotency), transactional
  outbox dispatcher, SMS OTP provider selection. No action now.

## Notes / things learned

- `pydantic` `EmailStr` rejects the reserved `.test` TLD — use `@example.com`
  in tests hitting the public prospect API.
- Profile submission **requires a photo** and a `StorageService`; fake it
  (`FakeStorageService` in `tests/e2e/conftest.py`).
- Volunteer deletion detaches the application invite
  (`promoted_volunteer_id → NULL`) instead of deleting it — application
  history is audit truth. Pending filters key off `status != 'promoted'`.
- The state machine was corrected to observed reality before wiring:
  approval from `prospect` is legal (public-signup flow), `SUBMIT_PROFILE`
  from `PROMOTED` is the post-approval profile-completion flow.
- The repo emits irrelevant Vercel/Next skill-injection noise on tool use —
  this is a Python/FastAPI backend on Vercel serverless; ignore unless doing
  actual Vercel config.
