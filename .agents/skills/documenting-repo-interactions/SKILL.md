---
name: documenting-repo-interactions
description: Verify and document repository interactions from current source. Use when adding or changing docs about ownership, API boundaries, generated clients, external systems, deployment tracks, or sibling repositories.
---

# Documenting Repo Interactions

Use this skill when changing documentation that describes ownership, data flow,
consumer boundaries, generated clients, deploy tracks, or sibling repositories.

## Workflow

1. Find the exact code paths for each claim in the current repo.
2. If a claim names a sibling repo, inspect that sibling checkout too.
3. Separate these states:
   - API or schema exists
   - API or schema is generated into a client
   - runtime code actively calls the API
   - production deployment currently exposes the behavior
4. Cite source files in durable docs when a boundary is easy to misunderstand.
5. Update stale docs in the same change when they would mislead the next agent.

## Current High-Risk Boundary

Do not write that `samfunnetibergen` consumes `kvarteret-personal` for public
events. Current public arrangement pages and feeds in `samfunnetibergen` read
from Sanity. `samfunnetibergen` still proxies volunteer prospects to
`kvarteret-personal`.
