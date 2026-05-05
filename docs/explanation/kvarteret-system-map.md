# Kvarteret System Map

This page explains how the Kvarteret repositories in scope relate to each other. It focuses on current production and preview boundaries, not old migration history.

`kvarteret-personal` is the central backend for personnel data, mobile-card data, event read APIs, and volunteer prospect intake. It stores most application state in Supabase Postgres and exposes a checked-in OpenAPI contract for generated clients.

`kvarteret-internbevis-rn` is the Expo React Native app used by volunteers. It depends on `kvarteret-personal` for mobile-card login/profile data, internal and public event reads, and the now-playing endpoint.

`samfunnetibergen` is the Next.js site for recruitment and public event display. The production site is `blifrivillig.no`, released from the `main` branch through a manual release. The next/preview site is `neste.samfunnetibergen`, deployed from the `develop` branch in the Vercel Preview environment. It calls `kvarteret-personal` server-side for public event reads and volunteer prospect submissions.

`frontend-eventside` is the internal event editor at `event.kvarteret.no`. It currently reads and writes event rows directly through Supabase. The schema for those event tables is owned by Alembic migrations in `kvarteret-personal`.

```mermaid
---
title: Kvarteret Repository Interaction Map
---
flowchart LR
    personal["kvarteret-personal\nFastAPI backend and admin UI"]
    internbevis["kvarteret-internbevis-rn\nVolunteer mobile app"]
    samfunnet["samfunnetibergen\nblifrivillig.no and preview"]
    eventside["frontend-eventside\nevent.kvarteret.no editor"]
    supabase["Supabase\nPostgres, Auth, Storage"]
    azure["Azure Blob Storage\nlegacy/personnel photos"]
    spotify["Spotify Web API\nnow playing"]
    smtp["SMTP provider\ntransactional email"]
    slack["Slack Incoming Webhook\nfeedback"]
    studentbergen["StudentBergen\nexternal event publication context"]
    posthog["PostHog\nanalytics in sibling apps"]
    sanity["Sanity\ncontent for samfunnetibergen"]

    internbevis -->|"mobile-card, events, now-playing API"| personal
    samfunnet -->|"events and volunteer prospects API"| personal
    eventside -->|"direct event CRUD"| supabase
    personal -->|"owns migrations and runtime reads/writes"| supabase
    personal -->|"photo fallback or legacy photo storage"| azure
    personal -->|"current playback and OAuth"| spotify
    personal -->|"access codes and onboarding mail"| smtp
    personal -->|"feedback messages"| slack
    samfunnet -->|"analytics events"| posthog
    samfunnet -->|"content reads"| sanity
    frontendEventsideNote["frontend-eventside uses StudentBergen docs and publication workflow context"]
    eventside --> frontendEventsideNote
    frontendEventsideNote --> studentbergen
```

## Data Direction

The event boundary is split today. `kvarteret-personal` owns the schema and public read API. `frontend-eventside` owns the editing UI and currently writes directly to Supabase. Public consumers should use `kvarteret-personal` APIs instead of direct table access.

The volunteer recruitment boundary is cleaner. `samfunnetibergen` validates the public form and proxies submissions to `kvarteret-personal`, which creates the registration records and sends any follow-up email through its configured email adapter.

The mobile-card boundary is owned by `kvarteret-personal`. The React Native app stores a signed session token and presents it as a bearer token for profile and internal event reads.

## Release Boundaries

`kvarteret-personal` owns its OpenAPI artifact. Consumers regenerate clients from `openapi.json`; they are not supposed to copy handwritten API shapes.

`samfunnetibergen` has two visible tracks: `main` to `blifrivillig.no` by manual release, and `develop` to `neste.samfunnetibergen` through Vercel Preview.

`kvarteret-internbevis-rn` ships through Expo/EAS and app-store release processes. Backend changes must be additive unless the supported app versions have already been updated.
