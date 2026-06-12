# Local Development

Use these commands from `/Users/kluvin/dev/kvarteret/kvarteret-personal`.

## Install

    make install

This installs Python dependencies with `uv` and frontend dependencies with `bun`.

## Start the Local Stack

The default development harness runs Postgres 17 in Docker, applies every
Alembic migration, and loads deterministic synthetic data:

    make dev-up
    make dev-run

The app should listen on `http://127.0.0.1:8000`.

Check health:

    curl http://127.0.0.1:8000/health

Expected body:

    {"status":"ok"}

The seeded admin login is:

    dev@kvarteret.dev / dev-password

Override it with `DEV_ADMIN_EMAIL` and `DEV_ADMIN_PASSWORD`. These settings are
refused outside `APP_ENV=development`.

When external services are not configured, development uses local adapters:

- email HTML is written to `.devdata/outbox/`
- uploaded photos are written to `.devdata/photos/`
- the configured development admin is authenticated without Supabase Auth

Reset or stop the database with:

    make dev-reset
    make dev-down

`make run` remains available for developers who already have a complete `.env`
and external service credentials.

## Development Data

The harness uses `scripts/dev/seed_synthetic.py` unless
`seeds/dev-snapshot.sql` exists. The synthetic seed is fake and deterministic.

Maintainers with production access may generate an anonymized snapshot:

    make dev-snapshot

The snapshot tool excludes sessions, integration tokens, access codes, rate
limits, audit payloads, and photos, then verifies identifying fields before
writing the file. `seeds/` is gitignored; snapshots contain organizational
history and must be distributed out of band, never committed.

## Build or Watch CSS

Build once:

    bun run build:css

Watch during UI work:

    make css-watch

## Run Tests

Run all tests:

    make test

Use an explicit database URL for database-backed checks:

    DATABASE_URL=sqlite+aiosqlite:////tmp/kvarteret-personal-tests.db make test

Run focused tests while working on one surface:

    uv run pytest tests/api/mobile_card/test_mobile_card_api.py
    uv run pytest tests/web/volunteers/test_volunteers_web.py

For the full layer-by-layer testing guide, including the Postgres-backed e2e
suite, see [Run the tests](run-tests.md).

## Regenerate OpenAPI

    make openapi

Verify the checked-in artifact:

    make openapi-check

When the API changes, update sibling generated clients. See [Update OpenAPI clients](update-openapi-clients.md).

## Check Schema Drift

Compare the configured database schema to the SQLAlchemy table metadata:

    make schema-drift

The restructure is complete: production and the SQLAlchemy metadata agree, so
this should report no drift against production or against a freshly migrated
database. CI runs it against a migrated disposable Postgres on every push.

## Common Local Failure Modes

If Docker is unavailable, use `make run` with a configured `.env`. If a local
adapter is unexpectedly inactive, check `APP_ENV` and the external-service
variables in [Configuration](../reference/configuration.md); configured
Supabase, SMTP, and Azure adapters take precedence over local fallbacks.

If `make run` is blocked by frontend tooling, a direct Python fallback is:

    uv run uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000

If a server-rendered page shows stale HTML after a write, inspect `app/main.py` first. HTML GET responses should use `Cache-Control: private, no-cache` and `Vary: Cookie, HX-Boosted, HX-Request`.
