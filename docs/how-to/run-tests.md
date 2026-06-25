# Run the Tests

The system has four test layers. Run the fast suite constantly, the full battery before pushing, and the e2e suite when touching the database, the unit of work, or the application lifecycle.

## Fast Suite (unit + web, ~15s)

    DATABASE_URL=sqlite+aiosqlite:////tmp/kv.db uv run pytest -q --ignore=tests/e2e

What it covers:

- **Pure logic** — the state-machine matrix (`tests/unit/domain/test_state_machine.py`) asserts every state×action pair.
- **Services against fakes** — repositories faked as plain classes; the rate limiter as `InMemoryRateLimiter`; sessions bound with `set_request_session(FakeSession())` on the ContextVar. Read-side tests monkeypatch the row-fetcher methods on the queries classes (`service.fetch_volunteer_shell_row = fake`).
- **Routes through the real ASGI app** — `tests/web/` and `tests/api/` build the actual app (all middleware) and override dependencies via `app.dependency_overrides`.

## Static Gates

    uv run ruff check .
    uv run lint-imports        # layers + domain-independence contracts
    DATABASE_URL=sqlite+aiosqlite:////tmp/kv-oas.db kv openapi --check
    kv audit                 # pip-audit

`lint-imports` is a real test: a cross-module service import fails the build.

## E2E (real stack on migrated Postgres)

Only SMTP and Azure storage are faked; migrations, the unit of work, repositories, the Postgres rate limiter, CHECK constraints, and the audit table are all real.

Set up a disposable database once:

    docker run -d --name kvarteret-e2e-pg -e POSTGRES_DB=kvarteret_personal \
      -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -p 55440:5432 postgres:17
    sleep 5

Apply the Supabase compatibility stubs (roles, `auth.uid()`, storage schema) — copy the SQL block from the `Prepare Supabase-compatible schemas` step in `.github/workflows/ci.yml` and pipe it through:

    docker exec -i kvarteret-e2e-pg psql -U postgres -d kvarteret_personal -v ON_ERROR_STOP=1 < stubs.sql

Migrate and run:

    export E2E_URL=postgresql+asyncpg://postgres:postgres@localhost:55440/kvarteret_personal
    DATABASE_URL=$E2E_URL uv run alembic upgrade head
    E2E_DATABASE_URL=$E2E_URL DATABASE_URL=$E2E_URL uv run pytest tests/e2e -q

The suite skips cleanly when `E2E_DATABASE_URL` is unset, truncates its tables per test, and asserts directly against the database with SQL. The two journeys are the full two-friend lifecycle (signup → emails → atomic group approval → deletion) and an induced-failure test proving group approval rolls back all-or-nothing.

Tear down when done:

    docker rm -f kvarteret-e2e-pg

## CI

`.github/workflows/ci.yml` runs the fast suite, the static gates, and a migration job (empty Postgres 17 → `alembic upgrade head` → `kv schema-drift`) on every push and PR, plus a weekly schedule so the quiet repo catches dependency rot.

## Production Smoke Checks

    curl -sI https://personal.kvarteret.no/health   # security headers + 200
    kv smoke-auth                                  # live create-login-cleanup roundtrip
    DATABASE_URL=<prod url> kv schema-drift        # prod schema matches metadata

## Extending the E2E Suite

The harness cost is paid; a new journey is ~50 lines in `tests/e2e/`. Good candidates: the solo prospect flow (trial shift → approve from `prospect`), reject, drop-member-then-approve-group, and the mobile-card access-code → session flow (which also exercises the Postgres rate limiter end to end).
