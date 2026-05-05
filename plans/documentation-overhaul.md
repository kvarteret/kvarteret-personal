# Overhaul Kvarteret Personal and System Documentation

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `PLANS.md`.

## Purpose / Big Picture

After this change, a new contributor should be able to open `README.md`, understand what `kvarteret-personal` owns today, and follow links into Diataxis-style documentation for learning, doing, looking up API facts, and understanding the wider Kvarteret system. The documentation must define the API boundaries between `kvarteret-personal`, `kvarteret-internbevis-rn`, `samfunnetibergen`, and `frontend-eventside`, and it must also document the third-party systems that `kvarteret-personal` calls or stores data in.

The observable outcome is documentation, not runtime behavior. A reviewer should see a `docs/` tree with purpose-based pages, a useful top-level README, a current issue list under `docs/issues/`, and an organization profile README that lists only the repos in scope and explains which repos depend on which services.

## Progress

- [x] (2026-05-05 08:05Z) Read `PLANS.md`, the existing `README.md`, `architecture.md`, and the old `plans/fastapi-rewrite.md` to identify stale migration-centered documentation.
- [x] (2026-05-05 08:05Z) Inspected current route wiring in `app/api/router.py`, `app/main.py`, and the concrete API modules for events, mobile-card, volunteer prospects, now-playing, media, and web admin routes.
- [x] (2026-05-05 08:05Z) Inspected the sibling repos `kvarteret-internbevis-rn`, `samfunnetibergen`, and `frontend-eventside` to verify actual API consumers and contracts rather than relying on memory.
- [x] (2026-05-05 08:05Z) Created the Diataxis documentation tree under `docs/`, including explanation, reference, how-to, tutorial, and issue pages.
- [x] (2026-05-05 08:05Z) Rewrote `README.md` so it describes the current service instead of the one-time migration.
- [x] (2026-05-05 08:05Z) Replaced stale top-level architecture prose with a compatibility pointer to the canonical architecture explanation under `docs/`.
- [x] (2026-05-05 08:05Z) Updated `/Users/kluvin/dev/kvarteret/.github-private/profile/README.md` with the requested organization repository map and interaction points.
- [x] (2026-05-05 08:05Z) Validated local Markdown links for `README.md`, `architecture.md`, all `docs/**/*.md`, and `plans/documentation-overhaul.md`.
- [x] (2026-05-05 08:05Z) Verified the organization profile README contains the requested `samfunnetibergen`, `blifrivillig.no`, and interaction-point content.
- [x] (2026-05-05 08:15Z) Investigated archive readiness for `Personaldatabase_Backend` and `Personaldatabase_Frontend` and updated the issue list with concrete blockers.
- [x] (2026-05-05 08:16Z) Updated the organization README after the user confirmed the old backend has been replaced by new clients and is archive-safe.

## Surprises & Discoveries

- Observation: `PLANS.md` already has uncommitted changes expanding the ExecPlan structure.
  Evidence: `git diff -- PLANS.md` shows the new long-form ExecPlan requirements. This plan follows that structure and does not modify `PLANS.md`.

- Observation: `kvarteret-personal` already exposes the new events API consumed by both `samfunnetibergen` and the React Native app, while `frontend-eventside` still writes event data directly through Supabase.
  Evidence: `samfunnetibergen/lib/events.ts` fetches `/api/v1/events` and `/api/v1/events/taxonomy`; `kvarteret-internbevis-rn/src/features/dashboard/data/eventsRepository.ts` uses the generated OpenAPI client for the same endpoints; `frontend-eventside/src/lib/services/events.ts` reads and writes `events`, `event_types`, `event_organizer_groups`, `event_organizer_group_memberships`, and `rooms` through Supabase.

- Observation: The current docs omit several production integrations.
  Evidence: `app/config.py` and runtime services show Supabase Postgres/Auth/Storage, Azure Blob Storage, SMTP, Spotify, Slack Incoming Webhooks, Vercel, and PostHog-facing consumer integrations.

- Observation: `Personaldatabase_Backend` is still live behind `api.kvarteret.no`.
  Evidence: DNS resolves `api.kvarteret.no` to `personaldatabasen-api.azurewebsites.net`, and `curl` to `/api/Debug/PingAsTilskuer` returns `401 Unauthorized` from `Server: Kestrel`.

- Observation: `Personaldatabase_Frontend` has weaker live evidence than the old backend.
  Evidence: DNS lookup for `intern.kvarteret.no` returned no records during the archive-readiness check, while the frontend repo still has a Docker Hub/Azure restart workflow.

## Decision Log

- Decision: Put canonical system and API boundary facts under `docs/reference/` and `docs/explanation/`, then make `README.md` a short portal into those docs.
  Rationale: The old README mixed setup, migration history, architecture, and operations. A short README plus purpose-based docs makes repeated facts easier to remove and keeps API boundaries easier to find.
  Date/Author: 2026-05-05 / Codex

- Decision: Treat `kvarteret-personal` as the schema owner for event tables, but document that `frontend-eventside` is currently a direct Supabase writer.
  Rationale: The repository README and migrations show event schema ownership moved here, but the sibling repo still performs event CRUD against Supabase. The docs should describe the real boundary and the desired source-of-truth boundary separately.
  Date/Author: 2026-05-05 / Codex

- Decision: Document `samfunnetibergen` production and preview behavior from the user's instruction, not just from the current checkout branch.
  Rationale: The local checkout is on `develop`, but the requested organization README needs release semantics: `blifrivillig.no` production comes from `main` plus manual release, and `neste.samfunnetibergen` comes from `develop` in Vercel Preview.
  Date/Author: 2026-05-05 / Codex

- Decision: Mark `Personaldatabase_Backend` and `Personaldatabase_Frontend` as replaced and archive-safe in the organization README.
  Rationale: The user confirmed the old backend has been replaced by new clients, so the organization profile should guide contributors to `kvarteret-personal` instead of preserving the old repos as active boundaries.
  Date/Author: 2026-05-05 / Codex

## Outcomes & Retrospective

- Outcome: The repository now has a purpose-based `docs/` tree with canonical pages for first-run onboarding, local development, OpenAPI client updates, deployment checks, API boundaries, external systems, configuration, system architecture, and current documentation issues.
  Date/Author: 2026-05-05 / Codex

- Outcome: The top-level README now describes the current FastAPI service and points readers into `docs/`. The old architecture file now points to the canonical docs instead of preserving stale migration-era content.
  Date/Author: 2026-05-05 / Codex

- Outcome: The organization profile README now lists the scoped repos and their interaction points, including the `samfunnetibergen` production/preview branch distinction requested by the user.
  Date/Author: 2026-05-05 / Codex

- Outcome: Local link validation passed for 14 Markdown files in `kvarteret-personal`, and a small assertion check passed for the organization profile README.
  Date/Author: 2026-05-05 / Codex

- Outcome: The issue list recorded the initial archive-readiness concern, then was updated after the user confirmed the old backend has been replaced by new clients and is safe to archive.
  Date/Author: 2026-05-05 / Codex

- Outcome: The organization profile README now separates active systems from replaced/archive-safe repos and points new clients at `personal.kvarteret.no`.
  Date/Author: 2026-05-05 / Codex

## Context and Orientation

`kvarteret-personal` is a FastAPI application. FastAPI is a Python web framework that serves both JSON API routes and server-rendered HTML pages. In this repository, the application factory is `app/main.py:create_app`, the route composition lives in `app/api/router.py`, `app/web/router.py`, `app/media/router.py`, and `app/system/router.py`, and the dependency graph is assembled in `app/runtime.py`.

The repository currently owns the personnel admin web UI, the mobile-card API for the volunteer app, public event read APIs, public volunteer prospect registration, the now-playing API backed by Spotify, media proxy routes, and database migrations for the Supabase Postgres schema. The checked-in API contract is `openapi.json`, generated by `make openapi`.

The sibling systems in scope are:

`kvarteret-internbevis-rn`: the Expo React Native app for volunteers. It calls `kvarteret-personal` for mobile-card login and profile data, internal/public events, and now-playing data. It generates a typed API client from `kvarteret-personal/openapi.json`.

`samfunnetibergen`: the Next.js site for `blifrivillig.no` and preview recruitment pages. It calls `kvarteret-personal` server-side for public events and for volunteer prospect submissions. Production uses the `main` branch with manual release; `develop` is deployed to the Vercel Preview environment for `neste.samfunnetibergen`.

`frontend-eventside`: the internal event editor at `event.kvarteret.no`. It currently writes event data directly to Supabase tables whose migrations are owned by `kvarteret-personal`.

The third-party systems in scope are Supabase Postgres, Supabase Auth, Supabase Storage, Azure Blob Storage, Spotify Web API, SMTP email, Slack Incoming Webhooks, Vercel, PostHog, Expo/EAS, Firebase App Distribution, Sanity, and StudentBergen. Some are direct dependencies of `kvarteret-personal`; others are dependencies of sibling repos that matter for the system map.

## Plan of Work

First, create `docs/README.md` as the documentation index. It should explain the Diataxis folders and point to the canonical docs.

Second, create explanation pages. `docs/explanation/kvarteret-system-map.md` should explain the Kvarteret system as a whole and include a Mermaid diagram with a title. `docs/explanation/kvarteret-personal-architecture.md` should explain the runtime architecture of this repo and include a Mermaid diagram with a title.

Third, create reference pages. `docs/reference/api-boundaries.md` should be the canonical list of API consumers, providers, endpoints, auth expectations, and contract generation. `docs/reference/external-systems.md` should be the canonical list of third-party systems and data direction. `docs/reference/configuration.md` should document the environment variables from `app/config.py` in grouped prose and concise lookup tables.

Fourth, create action-oriented pages. `docs/tutorials/first-local-run.md` should be a first-run learning path. `docs/how-to/local-development.md`, `docs/how-to/update-openapi-clients.md`, and `docs/how-to/deploy-and-runtime-checks.md` should give concrete commands for common tasks.

Fifth, create `docs/issues/current-documentation-issues.md` as the running issue list. This file should distinguish already-fixed documentation issues from open product or documentation questions discovered during the overhaul.

Sixth, rewrite `README.md` to describe the current application, current docs, and current commands. Keep migration material only as links or operational notes where it remains useful.

Seventh, replace `architecture.md` with a short compatibility pointer to `docs/explanation/kvarteret-personal-architecture.md` so stale architecture prose does not compete with the canonical page.

Eighth, update `/Users/kluvin/dev/kvarteret/.github-private/profile/README.md`. Keep the existing repository descriptions where they still apply, add `samfunnetibergen`, `kvarteret-personal`, and the interaction point section, and list only the repos in scope.

## Concrete Steps

Work from `/Users/kluvin/dev/kvarteret/kvarteret-personal`.

Create documentation folders:

    mkdir -p docs/explanation docs/reference docs/how-to docs/tutorials docs/issues plans

After editing, inspect the changed files:

    git diff -- README.md architecture.md docs plans/documentation-overhaul.md

Validate Markdown links that point to local files:

    uv run python - <<'PY'
    from pathlib import Path
    import re
    for path in [Path("README.md"), Path("architecture.md"), *Path("docs").rglob("*.md"), Path("plans/documentation-overhaul.md")]:
        text = path.read_text()
        for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text):
            target = match.group(1)
            if "://" in target or target.startswith("#") or target.startswith("mailto:"):
                continue
            clean = target.split("#", 1)[0]
            if clean and not (path.parent / clean).resolve().exists():
                raise SystemExit(f"{path}: missing link target {target}")
    PY

Optionally check rendered docs manually in a Markdown viewer. The docs do not change runtime code.

## Validation and Acceptance

Acceptance is met when:

`README.md` describes the current service and links to the new documentation entry point.

`docs/README.md` exists and links to tutorial, how-to, reference, explanation, and issue pages.

`docs/reference/api-boundaries.md` defines the boundaries for `kvarteret-internbevis-rn`, `samfunnetibergen`, and `frontend-eventside`.

`docs/reference/external-systems.md` documents the direct third-party dependencies of `kvarteret-personal` and the related third-party systems used by sibling repos.

`docs/issues/current-documentation-issues.md` contains the running issue list discovered during the overhaul.

The organization profile README at `/Users/kluvin/dev/kvarteret/.github-private/profile/README.md` lists only the scoped repositories and includes interaction points.

The local link-check command above exits with status 0.

## Idempotence and Recovery

All planned edits are documentation-only and can be reapplied safely. If a local link check fails, fix the path in the referencing document or create the intended target file. Do not modify the existing uncommitted code changes in `app/api/v1/events.py` or `tests/api/events/test_events_api.py`; those are outside the documentation scope.

If the organization profile README turns out to be the wrong repo, keep the edit as a local draft and move the same content to the correct `.github` profile repo later.

## Artifacts and Notes

Important evidence collected before editing:

    app/api/router.py includes /api/now-playing, /api/v1/events, /api/v1/mobile-card, /api/v1/volunteer-prospects, and /api/DigitalInternkort.
    samfunnetibergen/lib/events.ts fetches public events from https://personal.kvarteret.no/api/v1 by default.
    samfunnetibergen/app/api/volunteer-prospects/route.ts proxies public recruitment submissions to /api/v1/volunteer-prospects.
    kvarteret-internbevis-rn/src/features/auth/data/authRepository.ts calls /api/v1/mobile-card/access-codes, /sessions, and /me.
    kvarteret-internbevis-rn/src/features/dashboard/data/eventsRepository.ts calls /api/v1/events, /api/v1/events/taxonomy, and /api/v1/events/{event_id}.
    frontend-eventside/src/lib/services/events.ts still reads and writes event tables directly through Supabase.

## Interfaces and Dependencies

No runtime interfaces are changed by this documentation overhaul.

The documentation must describe these stable current interfaces:

`GET /api/v1/events`: public event list by default, optional internal events only with a valid mobile-card bearer token.

`GET /api/v1/events/taxonomy`: public taxonomy lookup for event types, organizer groups, and rooms.

`GET /api/v1/events/{event_id}`: event detail lookup.

`POST /api/v1/mobile-card/access-codes`: request a one-time mobile-card access code by email.

`POST /api/v1/mobile-card/sessions`: exchange email and access code for a signed mobile-card session token and card payload.

`GET /api/v1/mobile-card/me`: read the current mobile-card profile with a bearer token.

`POST /api/v1/mobile-card/client-events/session-logout`: accept diagnostic logout events from the mobile app.

`POST /api/v1/volunteer-prospects`: accept public recruitment leads from `samfunnetibergen`.

`GET /api/now-playing`: expose the shared Spotify now-playing state.

`POST /api/DigitalInternkort/RequestAccessTokenOnEmail` and `POST /api/DigitalInternkort/GetInternkortInformation`: deprecated compatibility endpoints for older clients.

Revision note 2026-05-05: Created this plan after reading the current repo, sibling consumers, and the updated `PLANS.md` requirements. The plan is documentation-only and explicitly avoids the existing uncommitted code edits.

Revision note 2026-05-05: Updated progress and outcomes after creating the docs tree, replacing stale README/architecture entry points, and updating the organization profile README. Remaining work is validation and any resulting fixes.

Revision note 2026-05-05: Recorded successful Markdown link validation and organization profile content checks. The documentation overhaul is complete unless review feedback asks for a different split or wording.

Revision note 2026-05-05: Added archive-readiness investigation results for the two legacy personaldatabase repos after live DNS, HTTP, GitHub metadata, CI workflow, and cross-repo reference checks.

Revision note 2026-05-05: Updated the archive recommendation after the user confirmed the old backend has been replaced by new clients. The organization README now treats both legacy personaldatabase repos as replaced and archive-safe.
