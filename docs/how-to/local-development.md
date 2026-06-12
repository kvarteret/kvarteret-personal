# Local Development

Use these commands from `/Users/kluvin/dev/kvarteret/kvarteret-personal`.

## Install

    make install

This installs Python dependencies with `uv` and frontend dependencies with `bun`.

## Run the Server

    make run

The app should listen on `http://127.0.0.1:8000`.

Check health:

    curl http://127.0.0.1:8000/health

Expected body:

    {"status":"ok"}

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

If protected pages fail because auth or storage is not configured, check the relevant environment variables in [Configuration](../reference/configuration.md).

If `make run` is blocked by frontend tooling, a direct Python fallback is:

    uv run uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000

If a server-rendered page shows stale HTML after a write, inspect `app/main.py` first. HTML GET responses should use `Cache-Control: private, no-cache` and `Vary: Cookie, HX-Boosted, HX-Request`.
