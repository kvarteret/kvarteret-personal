---
name: maintaining-api-boundaries
description: Maintain FastAPI, OpenAPI, generated-client, and sibling API boundaries. Use when changing routes, models, operation IDs, API docs, or consumer contracts.
---

# Maintaining API Boundaries

Use this skill when changing FastAPI routes, request/response models, operation
IDs, OpenAPI output, generated clients, or docs that explain sibling API use.

## Workflow

1. Inspect the route in `app/api/router.py` and the mounted module under
   `app/api/v1/` or the top-level API module.
2. Inspect Pydantic request and response models before changing field names or
   optionality.
3. Regenerate the contract:

   ```sh
   make openapi
   make openapi-check
   ```

4. Inspect `git diff -- openapi.json` for accidental field exposure or operation
   ID churn.
5. Check sibling consumers that actually use the changed boundary. Do not assume
   generated client code means runtime usage.

## Consumer Notes

- `kvarteret-internbevis-rn` uses mobile-card and now-playing runtime calls.
  Its current dashboard events repository reads Sanity, though generated event
  operations still exist in `src/core/api/kvarteret-personal`.
- `samfunnetibergen` currently posts volunteer prospects to this repo. Its public
  arrangement pages and feeds read Sanity.
- `frontend-eventside` is retired. Its stale direct Supabase event-table code is
  historical evidence only and is not a live coordination blocker.
