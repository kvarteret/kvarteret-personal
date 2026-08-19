# Closed handoff: June 2026 legacy restructure

This handoff is closed. Pull request #21, `restructure/m5-m9-completion`, was merged into `develop` as commit `ba97f3a`. The original push, CI, merge, deployment, and local-container checklist is obsolete and remains available in git history.

For the reasoning and as-built summary, read `plans/legacy-restructure.md`. For current setup and verification commands, read `docs/how-to/local-development.md` and `docs/how-to/run-tests.md`.

## Delivered in the merged change

- Request-scoped SQLAlchemy sessions and commit-before-external-effect behavior.
- Domain-owned tables, explicit service and repository seams, and import-linter boundary enforcement.
- An explicit volunteer-application state machine with transactional `domain_events` writes.
- Postgres-backed rate limiting, HMAC-SHA256 mobile access-code hashing, security headers, and enumeration-resistant public responses.
- A credential-free local Postgres harness, deterministic synthetic seed data, and Postgres lifecycle tests.

Later work replaced group applications with independent friend invitations and added a durable volunteer email outbox. Their plans are `plans/individual-friend-invitation-applications.md` and `plans/durable-email-and-posthog-observability.md`; the original handoff's deferred descriptions of those areas are no longer current.

## Follow-ups that remain separate

Auth consolidation was deliberately excluded from pull request #21. `docs/adr/002-auth-consolidation.md` records the intended direction, while current source and migrations determine what is actually implemented. The remaining coordinated work includes persistent role grants, adoption of permission dependencies across routes, local admin password verification, removal of obsolete identity-provider rows, and eventual GoTrue retirement.

Mobile-card sessions are still signed tokens without a server-side revocation table. Per-device expiry and revocation remain a separate API, migration, and mobile-client coordination project.

Do not treat either follow-up as shipped merely because permission or SMS protocols exist in source.

## Historical test credentials

The removed handoff contained hard-coded credentials for a disposable Docker container bound to `localhost`. They were synthetic development values, not production secrets. Current contributors should use the `kv` commands and current development documentation instead of recreating that transcript.

Revision note (2026-08-14): Replaced the obsolete active handoff with this closed post-merge note. Removed machine-specific operational steps and local test credentials, reconciled later friend-invitation and email-outbox work, and retained only unresolved follow-up boundaries.
