# Security Guidance

Use this for Claude, Codex, and Pi. Keep repository-specific checks in this file
when they are verified from source.

## Baseline

- Never commit secrets, tokens, cookies, local `.env` values, or Claude local
  settings.
- Validate all public input at the FastAPI boundary with Pydantic models and
  service-layer checks.
- Keep authentication and authorization checks close to the route or service
  boundary. Admin web routes should not rely on client-side controls.
- Prefer parameterized Supabase/Postgres access through existing repository and
  service helpers. Do not build SQL with string interpolation.
- Return user-safe error messages to browsers and clients; log operational
  context server-side without leaking secrets or bearer tokens.

## Repository-Specific Checks

- Public volunteer prospect intake is exposed by
  `app/api/v1/volunteer_prospects.py`; preserve anti-duplication and validation
  behavior when changing the form contract.
- Mobile-card endpoints issue and refresh bearer tokens. Treat response shapes as
  mobile-client contracts and keep changes additive unless supported app versions
  are verified.
- Media and document routes may proxy private personnel assets. Confirm access
  checks before changing storage URLs, redirects, or caching behavior.
- `openapi.json` is a public contract. Review generated schema changes for
  accidental exposure of internal fields.

## Before Commit

Run the narrow verification for the touched surface:

- API contract changes: `make openapi` then `make openapi-check`.
- Python behavior changes: targeted `uv run pytest ...` tests.
- Web/template changes: targeted web tests when available and browser/manual
  verification for changed flows.
- Dependency or exposed route changes: run the repository's security-sensitive
  tests or explain why they do not apply.
