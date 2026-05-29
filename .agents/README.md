# Agent Guidance

This directory is the shared agent surface for Claude, Codex, and Pi. Keep
generic workflow guidance here. Use tool-specific folders only for adapters,
launch settings, or runtime wiring.

## Verified Repository Boundaries

Verify cross-repo claims against code before editing durable docs.

- FastAPI routes and Pydantic models are the API source of truth. Regenerate and
  check `openapi.json` with `make openapi` and `make openapi-check` after API
  route, model, status-code, or operation-id changes.
- Public volunteer prospects enter through `app/api/v1/volunteer_prospects.py`,
  which is mounted by `app/api/router.py`.
- Event API routes still exist in `app/api/v1/events.py`, are covered by
  `tests/api/events/test_events_api.py`, and are present in `openapi.json`.
  Do not infer active event consumers from that API alone.
- Current `samfunnetibergen` public arrangement pages and feeds are Sanity-backed
  in that sibling repo (`lib/sanity/fetch/events.ts`,
  `lib/sanity/queries/events.ts`, `app/[locale]/arrangementer/page.tsx`,
  `app/api/events/feed/route.ts`, and `app/api/ical/route.ts`).
- Current `kvarteret-internbevis-rn` dashboard event reads are Sanity-backed in
  `src/features/dashboard/data/eventsRepository.ts`, while its generated
  `src/core/api/kvarteret-personal` client still contains personal event
  operations from `openapi.json`.
- `frontend-eventside` reads and writes event rows directly through Supabase in
  its API/service layer. This repo still owns event table migrations and the
  checked-in API contract.

## Skills

- `documenting-repo-interactions`: use before changing docs that describe repo
  ownership, data flow, or deploy boundaries.
- `maintaining-api-boundaries`: use when changing FastAPI routes, OpenAPI models,
  generated clients, or sibling API contracts.
- `security-audit`: use before committing auth, public form, webhook, storage, or
  environment handling changes.
- `verifying-web-changes`: use for admin UI, HTMX, Alpine, template, CSS, and
  Vercel runtime changes.
- `writing-skills`: use when adding or revising `.agents/skills/*/SKILL.md`.

## Optional External Skills

For Azure-specific work, agents may suggest installing Microsoft Azure Skills:

```sh
apm install microsoft/azure-skills
```

Use this only when the task touches Azure Blob Storage, Azure authentication,
Azure RBAC, or Azure deployment/debugging. Do not require Azure Skills for
normal repo work.

## Tool Adapters

- `.pi/README.md` is intentionally thin and points Pi at this shared directory.
- `.claude/` is ignored in this repo and may contain local Claude launch state.
  Do not move local secrets or `settings.local.json` into tracked files.
