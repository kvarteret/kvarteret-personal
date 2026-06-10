# ADR-002: Auth consolidation — in-application authorization and GoTrue retirement

**Status**: Accepted
**Date**: 2026-06-10
**Author**: Pi

## Context

`kvarteret-personal` currently splits authentication and authorization across
two systems:

1. **Supabase GoTrue** (`auth.users`) — stores credentials for both admins and
   volunteers, manages password hashing, and issues JWTs.
2. **Application tables** (`user_accounts`, `web_sessions`, `group_admin_memberships`)
   — stores admin roles, group admin assignments, and server-side session rows.

This split carries several problems:
- Volunteers exist in `auth.users` despite having no admin access — they are
  there only because the .NET-era system registered everyone in the identity
  store.
- Authorization (role checks, group scoping) is ad-hoc: routes check
  `current_user.role == UserRole.ADMIN` inline, with no central permission
  model.
- GoTrue is a vendor dependency for a system that only needs two verifications:
  ~a dozen admins proving they know a password, and volunteers proving they
  hold a contact channel already on file.
- The `user_accounts` ↔ `auth.users` linkage (via `auth_user_id` UUID) is a
  sync surface where a bug is a security incident.

## Decision

**Authorization moves entirely into the application.**  We define:

1. A `Permission` enum naming every guarded capability
   (`app/auth/permissions.py`).
2. Roles as named permission bundles, defined in code (not the database).
3. A `role_grants` table mapping user accounts to roles, with an optional
   `group_id` for scoped access (e.g. "course admin for Vaktetaten").
4. A `require_permission(permission)` FastAPI dependency that replaces all
   ad-hoc `role == UserRole.ADMIN` checks in routes.

**Admin passwords move in-house.**  We add a `password_hash` column (argon2)
to `user_accounts` and verify passwords locally.  The two cutover options
are: import GoTrue's bcrypt hashes and verify-then-rehash, or send password
reset emails.  The GoTrue login path is kept behind a setting until every
admin has logged in on the new path, then the gateway is deleted.

**Volunteers are removed from `auth.users`.**  Volunteer identity is
`volunteer_records`.  Volunteer credentials are mobile-card access codes
(hashed per M8), delivered over channels on file (email today, SMS in the
future).  Volunteers never needed GoTrue credentials.

**GoTrue is retired.**  When both populations are off it, the Supabase Auth
gateway, its settings, and its test doubles are removed.  Supabase's
remaining footprint is exactly: managed Postgres, PITR, development branches,
one storage bucket.

**An `SmsGateway` protocol is defined** (`app/infrastructure/sms/protocols.py`)
alongside the existing email protocol.  No implementation is shipped — the
email-code flow remains the credential until a provider is chosen.
Provider selection (Twilio/Vonage vs. Norwegian aggregator) is deferred.

## Alternatives considered

**Hosted IdP (Clerk, WorkOS, Auth0, Stytch, Firebase Auth, Cognito) — rejected.**
Each adds a second user store that must sync with personnel state.  The
verification work they'd replace is ~150 lines on infrastructure that already
exists.

**Self-hosted IdP (Keycloak, Ory, Zitadel, Authentik) — rejected.**
Operational burden at a 3-person, 10-h/week team size is disproportionate.

**Policy engine (Casbin, OPA, Cerbos) — rejected.**
The authorization rules depend on group membership, role assignments, and
lifecycle state — all in the personnel database.  Mirroring them into a
policy engine creates the same sync surface as a vendor IdP, with added
latency and operational cost.  A `Permission` enum + role bundles in code
is the right level of complexity for this team size.

## Consequences

- Every admin route is guarded by `require_permission` instead of ad-hoc
  `role ==` checks.  Adding a new permission requires updating the enum
  and role bundles — both in one file.
- The `role_grants` table provides an audit trail of who granted what role
  to whom and when.
- Group-scoped permissions (e.g. "course admin for Vaktetaten") are handled
  by the optional `group_id` on `role_grants`.
- Removing volunteers from `auth.users` eliminates ~100 rows from the vendor
  identity store with no user-visible impact — volunteers never used those
  credentials.
- The `SmsGateway` protocol exists so that adding SMS OTP is a configuration
  change (pick a provider, implement the protocol), not a design change.
