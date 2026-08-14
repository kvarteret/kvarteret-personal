# API Boundaries

This page is the canonical reference for API boundaries between `kvarteret-personal` and the Kvarteret repositories in scope.

## Source of Truth

FastAPI route declarations and Pydantic response models in `kvarteret-personal` are the source of truth for the HTTP API. The checked-in artifact is `openapi.json`.

After changing API routes, request models, response models, or operation IDs, run:

    kv openapi

Before committing an API change, run:

    kv openapi --check

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

Requests a one-time access code for an email address. The endpoint intentionally returns `202` for unknown or duplicate people so the caller cannot use it to enumerate valid volunteer emails. Rate limits are Postgres-backed (they hold across serverless instances) and return `429`. Codes are single-use and stored only as keyed hashes; a new code is generated for every request.

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

`samfunnetibergen/apps/web/src/app/api/volunteer-prospects/route.ts` validates the
public recruitment form, then posts server-to-server to
`POST /api/v1/volunteer-prospects`.
Sanity choice slugs are forwarded unchanged. Most choices resolve directly
through Personal's stable, unique `groups.slug` column. Public bar-area choices
such as Halvtimen and Grøndahls instead resolve to a suggested role in the
operational Skjenkegruppen parent group. Personal snapshots both submitted
choice labels on the application so this many-to-one routing does not erase
what the applicant selected. Only the primary choice controls the suggested
group and role used during promotion; the optional secondary choice is review
metadata. Unknown slugs are rejected and public requests cannot create
organizational groups or roles.

Direct group slugs use the same deterministic Norwegian-safe generation rule
in both repositories. The explicit bar-area routing table is owned by Personal
because it maps public Sanity choices to Personal roles. An established group
slug is immutable even if the group's display name is later changed.

The request body accepts `friend_emails` (up to two). When present, the backend creates one ordinary application for the submitter and one ordinary application per friend, linked by invitation relationship records. Each friend gets a personal `/apply/{token}` link delivered by email; applications are reviewed and approved independently. Field-level validation errors for friend emails come back under `fieldErrors.friendEmails`.

### Volunteer-prospect request authentication

Personal accepts prospect creation only from a caller that holds the shared
`VOLUNTEER_PROSPECT_HMAC_SECRET`. The website signs the exact serialized JSON
body in
`samfunnetibergen/apps/web/src/lib/integrations/kvarteret-personal/volunteer-prospect-signing.ts`.
Personal verifies it in `app/api/request_auth.py` before the application service
runs. The secret is server-only and must never use a browser-visible
`NEXT_PUBLIC_*` variable.

Each request carries:

    X-Kvarteret-Timestamp: <Unix seconds>
    X-Kvarteret-Nonce: <lowercase UUID>
    X-Kvarteret-Signature: v1=<64 lowercase HMAC-SHA256 hex characters>

The signed message contains the protocol version, timestamp, nonce, HTTP method,
route path, and SHA-256 digest of the exact body bytes. Personal permits at most
five minutes of clock skew and consumes each verified nonce once through the
Postgres-backed rate limiter. Missing, stale, altered, malformed, and replayed
requests fail before prospect creation. HMAC authenticates the server holding
the secret; it does not prove that a human submitted the website form.

For the initial cutover, provision the same secret in both Vercel projects,
deploy `samfunnetibergen` signing first, and then deploy Personal enforcement;
the old Personal route safely ignores the added headers. To rotate without
downtime later, put the new value in Personal's
`VOLUNTEER_PROSPECT_HMAC_SECRET` and the old value in
`VOLUNTEER_PROSPECT_HMAC_PREVIOUS_SECRET`; deploy Personal, switch the website
to the new value, verify submissions, and finally remove the previous value.
There is deliberately no unsigned compatibility mode.

## `frontend-eventside`

`frontend-eventside` was the event editing surface at `event.kvarteret.no`.
Its source still contains direct Supabase queries against the retired event
tables. The repo is retired, so those source references are historical evidence
only and are not a coordination requirement for `kvarteret-personal` table
removal.

## Removed Legacy Boundary

`POST /api/DigitalInternkort/RequestAccessTokenOnEmail` and `POST /api/DigitalInternkort/GetInternkortInformation` were permanently removed on 2026-06-10 as part of the legacy restructure (M4). The four-week traffic gate was waived by the product owner. Pre-v1 app installs that called these paths lose mobile-card access and must update to the v1 mobile-card API at `/api/v1/mobile-card/*`.
