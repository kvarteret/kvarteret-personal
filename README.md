# Kvarteret Personal

`kvarteret-personal` is the current FastAPI backend and server-rendered admin UI for Kvarteret personnel workflows.

It owns:

- the personnel admin UI at `personal.kvarteret.no`
- Supabase Postgres migrations for personnel, auth-support, registration, and event tables
- the mobile-card API used by `kvarteret-internbevis-rn`
- event read APIs exposed in `openapi.json`
- public volunteer prospect intake used by `blifrivillig.no`
- media proxy routes for private personnel photos
- the Spotify-backed now-playing API
- the checked-in OpenAPI contract in `openapi.json`

The documentation home is [docs/README.md](docs/README.md).

## Quick Start

Install dependencies:

    uv sync
    bun install

Run the app:

    make run

Check health:

    curl http://127.0.0.1:8000/health

Expected body:

    {"status":"ok"}

The root web page redirects to `/login` when there is no admin session.

## Common Commands

    make install
    make run
    make css-watch
    make test
    make openapi
    make openapi-check
    make smoke-auth
Use [Local development](docs/how-to/local-development.md) for daily workflows.

## API Contract

FastAPI is the source of truth for the API contract. `openapi.json` is checked in so sibling clients can generate stable types from git history.

After changing API routes, request models, response models, or operation IDs:

    make openapi

Before committing API changes:

    make openapi-check

Consumer boundaries and client regeneration are documented in [API boundaries](docs/reference/api-boundaries.md) and [Update OpenAPI clients](docs/how-to/update-openapi-clients.md).

## System Boundaries

The important sibling boundaries are:

- `kvarteret-internbevis-rn` calls mobile-card and now-playing APIs; its generated personal client still includes event operations.
- `samfunnetibergen` proxies volunteer prospect submissions; its current public arrangement pages and feeds are Sanity-backed.
- `frontend-eventside` currently writes event tables directly through Supabase, while this repo owns the event schema migrations and public read API.

See [Kvarteret system map](docs/explanation/kvarteret-system-map.md) for the full diagram.

## External Systems

Direct runtime dependencies include Supabase Postgres, Supabase Auth, Azure Blob Storage, Spotify, SMTP, Slack Incoming Webhooks, Linear, and Vercel.

See [External systems](docs/reference/external-systems.md) and [Configuration](docs/reference/configuration.md).

## Deployment Shape

Vercel loads `api/index.py`, which exposes a module-level ASGI app from `app.main:create_app`.

The Vercel build runs the CSS/static preparation steps so `/static/...` assets are served from `public/static`, while non-static routes are rewritten to FastAPI.

Operational checks are documented in [Deploy and runtime checks](docs/how-to/deploy-and-runtime-checks.md).

## Historical Migration Notes

The old one-time rewrite and migration plan is preserved in [plans/fastapi-rewrite.md](plans/fastapi-rewrite.md). Treat it as history and implementation evidence, not as the current architecture entry point.

Current documentation issues are tracked in [docs/issues/current-documentation-issues.md](docs/issues/current-documentation-issues.md).
