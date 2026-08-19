# Historical documentation overhaul

This document records the documentation overhaul completed on 2026-05-05. It is a retrospective, not a current system map. Start with `README.md` and `docs/README.md` for current behavior. Use git history if the original execution transcript or its point-in-time repository investigation is needed.

The work followed the repository-level `PLANS.md` guidance. This shorter version keeps the decisions and outcomes while removing machine-specific paths and claims that later architecture changes superseded.

## Purpose / Big Picture

The overhaul changed the repository from migration-centered documentation into a contributor-oriented documentation set. A new contributor could start at the top-level README, follow a first-run tutorial, find operational how-to guides, look up API and configuration facts, and understand the wider Kvarteret system without reading the original FastAPI rewrite plan.

The observable result was a purpose-based `docs/` tree, a shorter top-level README, a canonical architecture explanation, a current-issues page, and a separately maintained organization-profile overview.

## Progress

- [x] (2026-05-05) Read the application, routes, configuration, sibling consumers, legacy repositories, and the existing migration documentation.
- [x] (2026-05-05) Created tutorial, how-to, reference, explanation, and issue sections under `docs/`.
- [x] (2026-05-05) Rewrote `README.md` as a short service overview and documentation portal.
- [x] (2026-05-05) Replaced the old top-level architecture narrative with a pointer to the canonical explanation.
- [x] (2026-05-05) Updated the private organization-profile repository with a repository map and interaction points.
- [x] (2026-05-05) Validated local Markdown links and reviewed the organization-profile content.
- [x] (2026-05-05) Recorded the product decision that the two old personal-database repositories were replaced and safe to archive.

## Surprises & Discoveries

- Observation: The old README described the repository as an unfinished migration even though the FastAPI service was already the active codebase.
  Evidence: the overhaul replaced migration instructions with the service summary and linked the one-time rewrite plan only as history.

- Observation: Repository ownership, generated API presence, runtime consumption, and production deployment are different facts.
  Evidence: sibling repositories contained generated or direct event integrations during the original investigation, but later work retired the Personal event API and tables. Current public event pages and feeds in `samfunnetibergen` read from Sanity.

- Observation: Organization-level documentation lives in a separate private repository.
  Evidence: the profile README could be updated and validated alongside this work, but it required its own review and commit boundary.

## Decision Log

- Decision: Organize durable documentation by reader need and keep `README.md` short.
  Rationale: Tutorials, how-to guides, reference material, and explanations age differently. Separating them makes current facts easier to find and update.
  Date/Author: 2026-05-05 / project team

- Decision: Keep API ownership and sibling-runtime claims in canonical reference and explanation pages.
  Rationale: Repeating those claims across plans and READMEs made stale boundaries look current.
  Date/Author: 2026-05-05 / project team

- Decision: Preserve the original FastAPI rewrite plan as historical evidence rather than as the architecture entry point.
  Rationale: It records useful migration decisions, but its commands, intermediate state, and deployment observations are not current operating instructions.
  Date/Author: 2026-05-05 / project team

- Decision: Treat the legacy personal-database repositories as replaced and archive-safe after product confirmation.
  Rationale: New contributors should be directed to `kvarteret-personal`, while useful legacy history can remain available in archived repositories.
  Date/Author: 2026-05-05 / product decision

## Outcomes & Retrospective

The repository gained `docs/README.md`, a first-run tutorial, local-development and deployment how-to guides, API/configuration/external-system references, architecture and system-map explanations, and a running documentation-issues page. The top-level README became a stable entry point rather than a migration log.

Some point-in-time boundary findings were superseded within the following months. In particular, Personal's event API and event tables were retired, `frontend-eventside` became historical only, and current `samfunnetibergen` arrangement pages and feeds became Sanity-backed. The maintained pages under `docs/` now describe those boundaries; this retrospective intentionally does not reproduce the obsolete endpoint list.

## Context and Orientation

`kvarteret-personal` serves a FastAPI JSON API and server-rendered admin UI. `app/main.py:create_app` creates the application, `app/api/router.py` composes current JSON routes, and `app/runtime.py` builds runtime dependencies.

Current documentation ownership is:

- `README.md` for a concise service overview and common commands.
- `docs/README.md` for the documentation index.
- `docs/reference/api-boundaries.md` for API ownership, generated clients, and active runtime consumers.
- `docs/reference/external-systems.md` for third-party services and data direction.
- `docs/reference/configuration.md` for settings.
- `docs/explanation/kvarteret-personal-architecture.md` and `docs/explanation/kvarteret-system-map.md` for architecture and cross-repository context.
- `docs/issues/current-documentation-issues.md` for known documentation gaps and external follow-ups.

The organization-profile README is maintained in a separate private repository. Refer to it by repository purpose, not by a contributor's absolute filesystem path.

## Work Performed

The original change created the `docs/` index and its purpose-based subdirectories, rewrote the repository README, replaced stale top-level architecture prose, and added a running issue list. It also inspected sibling source before documenting interactions and updated the private organization profile separately.

The work deliberately did not change runtime code. It documented the source as it existed on 2026-05-05 and recorded uncertainty where source, DNS, repository metadata, and product intent did not agree.

## Validation and Acceptance

The overhaul was accepted when the top-level README linked into every documentation category, local Markdown links resolved, and the private organization profile contained the agreed repository map and interaction points.

For current documentation changes, validate links from the repository root and inspect changed claims against source rather than copying the original point-in-time evidence:

    git diff --check
    rg -n '/Users/' README.md docs plans

When a change affects API routes, models, status codes, or operation IDs, also run:

    kv openapi --check

## Idempotence and Recovery

Documentation edits are safe to repeat. If a local link fails, correct the reference or restore the intended target. Changes to the private organization-profile repository must be reviewed and committed there; this repository must not embed its local checkout path or private contents.

Historical claims should be phrased with dates. When implementation changes a boundary, update the canonical page under `docs/` and leave this retrospective as a record of the completed overhaul rather than extending it into a second source of truth.

## Interfaces and Dependencies

This documentation change introduced no runtime interface. FastAPI routes and Pydantic models are the API source of truth, `openapi.json` is the checked generated contract, and current cross-repository interactions are maintained in `docs/reference/api-boundaries.md`.

As of this rewrite, the adjacent `samfunnetibergen` website still proxies public volunteer prospects to `POST /api/v1/volunteer-prospects`, while its current public event pages and feeds read from Sanity. The Personal events API is intentionally absent from `openapi.json`, and `frontend-eventside` is retired.

Revision note (2026-08-14): Replaced the completed 2026-05-05 execution transcript with a dated retrospective. Removed absolute private-repository paths and obsolete current-tense event/API claims, and linked readers to the maintained documentation instead.
