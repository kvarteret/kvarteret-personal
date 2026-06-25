# Local Development

Use these commands from `/Users/kluvin/dev/kvarteret/kvarteret-personal`.

## Install

    kv install

This installs Python dependencies with `uv` and frontend dependencies with `bun`.

## Start the Local Stack

The default development harness runs Postgres 17 in Docker, applies every
Alembic migration, loads deterministic synthetic data, and serves the app —
all as panes in one phrocs/mprocs session:

    kv start

The `kv` CLI lives in the sibling [infra repo](https://github.com/kvarteret/infra)
and is put on PATH by mise in either repo. Typing `kvarteret` (or `kv`) with no
arguments shows an interactive menu of all commands; `kv info` prints the URLs
and credentials below at any time.

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

    kv nuke
    kv stop

`kv run` remains available for developers who already have a complete `.env`
and external service credentials.

## Development Data

The harness uses `scripts/dev/seed_synthetic.py` unless
`seeds/dev-snapshot.sql` exists. The synthetic seed is fake and deterministic.

Maintainers with production access may generate an anonymized snapshot:

    kv snapshot

The snapshot tool excludes sessions, integration tokens, access codes, rate
limits, audit payloads, and photos, then verifies identifying fields before
writing the file. `seeds/` is gitignored; snapshots contain organizational
history and must be distributed out of band, never committed.

## Build or Watch CSS

Build once:

    bun run build:css

Watch during UI work:

    kv css-watch

## Run Tests

Run all tests:

    kv test

Use an explicit database URL for database-backed checks:

    DATABASE_URL=sqlite+aiosqlite:////tmp/kvarteret-personal-tests.db kv test

Run focused tests while working on one surface:

    uv run pytest tests/api/mobile_card/test_mobile_card_api.py
    uv run pytest tests/web/volunteers/test_volunteers_web.py

For the full layer-by-layer testing guide, including the Postgres-backed e2e
suite, see [Run the tests](run-tests.md).

## Regenerate OpenAPI

    kv openapi

Verify the checked-in artifact:

    kv openapi --check

When the API changes, update sibling generated clients. See [Update OpenAPI clients](update-openapi-clients.md).

## Check Schema Drift

Compare the configured database schema to the SQLAlchemy table metadata:

    kv schema-drift

The restructure is complete: production and the SQLAlchemy metadata agree, so
this should report no drift against production or against a freshly migrated
database. CI runs it against a migrated disposable Postgres on every push.

## Common Local Failure Modes

If Docker is unavailable, use `kv run` with a configured `.env`. If a local
adapter is unexpectedly inactive, check `APP_ENV` and the external-service
variables in [Configuration](../reference/configuration.md); configured
Supabase, SMTP, and Azure adapters take precedence over local fallbacks.

If `kv run` is blocked by frontend tooling, a direct Python fallback is:

    uv run uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000

If a server-rendered page shows stale HTML after a write, inspect `app/main.py` first. HTML GET responses should use `Cache-Control: private, no-cache` and `Vary: Cookie, HX-Boosted, HX-Request`.
