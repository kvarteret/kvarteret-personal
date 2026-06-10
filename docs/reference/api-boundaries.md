# API Boundaries

This page is the canonical reference for API boundaries between `kvarteret-personal` and the Kvarteret repositories in scope.

## Source of Truth

FastAPI route declarations and Pydantic response models in `kvarteret-personal` are the source of truth for the HTTP API. The checked-in artifact is `openapi.json`.

After changing API routes, request models, response models, or operation IDs, run:

    make openapi

Before committing an API change, run:

    make openapi-check

Consumers that generate typed clients should regenerate from `openapi.json`, preferably from a sibling checkout during local development or from the `develop` branch artifact when consuming remotely.

## Boundary Summary

| Consumer | Depends on | Boundary | Current state |
| --- | --- | --- | --- |
| `kvarteret-internbevis-rn` | `kvarteret-personal` and Sanity | Mobile-card, now-playing, generated personal API client, Sanity dashboard events | Mobile-card and now-playing are runtime API calls; current dashboard event reads are Sanity-backed; generated event operations are retired |
| `samfunnetibergen` | `kvarteret-personal` and Sanity | Volunteer prospects, Sanity public arrangements | Server-side volunteer prospect proxy; public arrangement pages and feeds are Sanity-backed |
| `frontend-eventside` | Retired Supabase event tables | Retired event editing | Retired repo; stale source references are historical and not a live dependency |
| `kvarteret-personal` | Supabase, Azure, Spotify, SMTP, Slack | Third-party services | Runtime adapters documented in [External systems](external-systems.md) |

## `kvarteret-internbevis-rn`

The React Native app defaults to:

    EXPO_PUBLIC_KVARTERET_PERSONAL_API_BASE_URL=https://personal.kvarteret.no/api/v1
    EXPO_PUBLIC_INTERNKORT_BASE_URL=https://personal.kvarteret.no/api/v1/mobile-card

It generates a client from `openapi.json` into `src/core/api/kvarteret-personal`. The generator first prefers a sibling `../kvarteret-personal/openapi.json`, then falls back to the remote `develop` artifact.

### Mobile-card API

`POST /api/v1/mobile-card/access-codes`

Requests a one-time access code for an email address. The endpoint intentionally returns `202` for unknown or duplicate people so the caller cannot use it to enumerate valid volunteer emails. Rate limits return `429`.

`POST /api/v1/mobile-card/sessions`

Exchanges an email and access code for a signed session token and a mobile-card profile. Current supported app versions pass `include_role_history=true` because older strict parsers needed a compatibility gate for additive response fields.

`GET /api/v1/mobile-card/me`

Reads the current profile with `Authorization: Bearer <mobile-card-session-token>`. The backend may return `X-Mobile-Card-Session-Token` when it renews the session.

`POST /api/v1/mobile-card/client-events/session-logout`

Accepts diagnostics when the mobile app logs a user out due to missing or invalid local credentials. This endpoint is write-only telemetry and returns `202`.

### Events API

The old `GET /api/v1/events`, `GET /api/v1/events/taxonomy`, and
`GET /api/v1/events/{event_id}` operations are retired. They are intentionally
absent from `openapi.json`.

### Now-playing API

`GET /api/now-playing`

The app derives the personal base URL from the configured mobile-card base URL and calls this endpoint for shared Grondahls now-playing state. It expects `authorized`, `hasTrack`, `isPlaybackActive`, nullable track fields, and `connectUrl`.

## `samfunnetibergen`

`samfunnetibergen` production is `blifrivillig.no`, released from `main` by manual release. `neste.samfunnetibergen` uses the `develop` branch in the Vercel Preview environment.

The site defaults to:

    PERSONAL_APP_BASE_URL=https://personal.kvarteret.no

Current public arrangement pages and feeds read from Sanity, not from
`kvarteret-personal`. Verified sibling paths include
`lib/sanity/fetch/events.ts`, `lib/sanity/queries/events.ts`,
`app/[locale]/arrangementer/page.tsx`, `app/api/events/feed/route.ts`, and
`app/api/ical/route.ts`.

`app/api/volunteer-prospects/route.ts` validates the public recruitment form, then posts to `POST /api/v1/volunteer-prospects`. It returns upstream validation errors to the browser and records PostHog server-side events when a PostHog distinct id is provided by the client.

## `frontend-eventside`

`frontend-eventside` was the event editing surface at `event.kvarteret.no`.
Its source still contains direct Supabase queries against the retired event
tables. The repo is retired, so those source references are historical evidence
only and are not a coordination requirement for `kvarteret-personal` table
removal.

## Deprecated Compatibility Boundary

`POST /api/DigitalInternkort/RequestAccessTokenOnEmail` and `POST /api/DigitalInternkort/GetInternkortInformation` are deprecated compatibility endpoints for older clients. New code should use `/api/v1/mobile-card/*`.

Do not remove these endpoints until all supported clients have moved to the v1 mobile-card API and release data confirms that older app versions no longer need them.
