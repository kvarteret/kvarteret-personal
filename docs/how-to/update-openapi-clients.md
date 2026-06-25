# Update OpenAPI Clients

Use this guide when changing any route path, request body, response model, status code, or operation id used by another repo.

## 1. Update the Backend Contract

From `kvarteret-personal`:

    kv openapi
    kv openapi --check

Commit `openapi.json` together with the backend change.

## 2. Update `kvarteret-internbevis-rn`

From `/Users/kluvin/dev/kvarteret/kvarteret-internbevis-rn`:

    npm run api:generate

The generator prefers the sibling `../kvarteret-personal/openapi.json` when present. Run the app tests that cover the changed surface.

For mobile-card response changes, keep backend responses additive. Installed app versions can remain in use after the backend deploys. Do not remove fields or change parser-sensitive shapes until the supported app versions are confirmed.

## 3. Update `samfunnetibergen`

From `/Users/kluvin/dev/kvarteret/samfunnetibergen`:

    npm run api:sync

This runs `../infra/bin/kv openapi` and regenerates the generated client/snapshot. Current public arrangement pages and feeds in `samfunnetibergen` are Sanity-backed. The retired personal event API is not a runtime `samfunnetibergen` dependency.

## 4. Record retired `frontend-eventside` impact

`frontend-eventside` is retired. Its source still contains stale direct
Supabase event-table code at historical paths such as:

    /Users/kluvin/dev/kvarteret/frontend-eventside/src/lib/services/events.ts
    /Users/kluvin/dev/kvarteret/frontend-eventside/src/lib/services/types.ts
    /Users/kluvin/dev/kvarteret/frontend-eventside/src/components/form

These references are not a live client-regeneration requirement. If
`frontend-eventside` is ever resurrected, rebuild it against the then-current
event source instead of the retired `kvarteret-personal` event tables.

## 5. Acceptance

The backend `openapi.json` is current, relevant sibling generated clients are updated, and consumer tests pass for the changed boundary.
