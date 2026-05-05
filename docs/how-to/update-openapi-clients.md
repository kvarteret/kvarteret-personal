# Update OpenAPI Clients

Use this guide when changing any route path, request body, response model, status code, or operation id used by another repo.

## 1. Update the Backend Contract

From `kvarteret-personal`:

    make openapi
    make openapi-check

Commit `openapi.json` together with the backend change.

## 2. Update `kvarteret-internbevis-rn`

From `/Users/kluvin/dev/kvarteret/kvarteret-internbevis-rn`:

    npm run api:generate

The generator prefers the sibling `../kvarteret-personal/openapi.json` when present. Run the app tests that cover the changed surface.

For mobile-card response changes, keep backend responses additive. Installed app versions can remain in use after the backend deploys. Do not remove fields or change parser-sensitive shapes until the supported app versions are confirmed.

## 3. Update `samfunnetibergen`

From `/Users/kluvin/dev/kvarteret/samfunnetibergen`:

    npm run api:sync

This runs `make -C ../kvarteret-personal openapi` and regenerates the generated client/snapshot. The public events code currently has hand-written fetch types in `lib/events.ts`, so verify those types too when event fields change.

## 4. Check `frontend-eventside`

`frontend-eventside` currently writes event data directly through Supabase instead of a generated `kvarteret-personal` API client. When event schema changes, inspect:

    /Users/kluvin/dev/kvarteret/frontend-eventside/src/lib/services/events.ts
    /Users/kluvin/dev/kvarteret/frontend-eventside/src/lib/services/types.ts
    /Users/kluvin/dev/kvarteret/frontend-eventside/src/components/form

Schema changes must be compatible with the direct Supabase writer until event writes move behind a backend API.

## 5. Acceptance

The backend `openapi.json` is current, relevant sibling generated clients are updated, and consumer tests pass for the changed boundary.
