---
name: security-audit
description: Focused security audit for auth, public forms, tokens, storage, webhooks, outbound integrations, admin routes, or environment handling.
---

# Security Audit

Use this skill before committing changes to auth, public forms, tokens, storage,
webhooks, outbound integrations, admin routes, or environment handling.

## Checklist

- No secrets, cookies, bearer tokens, credentials, or local settings are added to
  git.
- Public route inputs are validated with Pydantic models and service-level
  domain checks.
- Authorization is enforced server-side for admin, personnel, media, and
  mobile-card data.
- Mobile-card token changes are additive and do not expose profile data to
  unauthenticated callers.
- Supabase/Postgres access uses established helpers or parameterized APIs.
- External service failures return user-safe messages and preserve server-side
  diagnostic context.
- OpenAPI changes do not expose internal-only fields.

## Verification

Run the narrow tests for the touched surface. For API contract changes, also run
`make openapi-check`.
