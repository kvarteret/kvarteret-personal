## Architecture Review & Bug Hunt — Observations

### 🔴 Bugs found

**1. login_service.py — unhandled NotConfiguredError**
`login_with_bridge()` calls `supabase_auth.sign_in_with_password()` which can raise
`NotConfiguredError` (from UnconfiguredSupabaseAuthGateway). This propagates unhandled,
resulting in a 500 error instead of a proper "service unavailable" message.

**2. login_service.py — legacy migration has no rollback**
If `create_user_from_legacy` succeeds but `upsert_user_account` fails, the Supabase user
exists without corresponding database records. No rollback mechanism.
→ User says we can remove legacy migration entirely (6 months of migration is enough).

### 🟡 Observations

**3. mobile_card/service.py — `_maybe_renew_session_token` fallback**
Line 533: `decoded.person_id or 0` — if person_id is somehow 0 (which means "review card"),
the `or 0` keeps it at 0. Harmless now but fragile. Redundant since validation already
guarantees person_id is int.

**4. session_store.py — cache expiry check correct**
`load_authenticated_user()` properly checks `cached.web_session.expires_at <= now` before
returning cached data.

**5. cookies.py — URLSafeSerializer without max_age**
Session cookie uses `URLSafeSerializer` (not TimedSerializer). Expiry is checked at
session level in cache/DB, so this is acceptable. But `URLSafeTimedSerializer` would add
defense-in-depth against forged cookies with old session IDs.

**6. volunteers/service.py — upload_photo has proper rollback**
Upload → save DB → on DB failure, remove uploaded file. Correct pattern.

**7. volunteers/service.py — delete_volunteer order is correct**
DB delete first, then best-effort storage cleanup. Orphaned files are acceptable;
incomplete deletes would be worse.

### 🟢 Good patterns

- `_sanitize_filename` prevents path traversal via `Path(filename).name`
- `hmac.compare_digest` in legacy password verification (timing-safe)
- DI container cleanly separates all services
- `_best_effort_remove` pattern for non-critical cleanup
- upload_photo rollback pattern (upload → save → rollback on error)

### Next to review
- [ ] web routes — CSRF, auth guards, error handling patterns
- [ ] domain/events — event service caching
- [ ] domain/volunteer_applications — application flow edge cases
- [ ] infrastructure/storage — Azure blob + Supabase split
- [ ] infrastructure/email — SMTP error handling
- [ ] Remove legacy auth (per user request)

### 🔴 More bugs

**8. mobile_card/service.py — rate limit TOCTOU race**
`create_session()` checks rate limit FIRST, then validates code, then increments
AFTER failure. Two concurrent requests can both pass the check before either increments.
Fix: increment atomically BEFORE validation, decrement on success.

**9. events/service.py — pagination off-by-design**
`list_events` fetches 3x limit, maps rows (some return None), then slices. If all
fetched rows fail mapping, response is empty even with more events in DB. Standard
for internal admin but could confuse API consumers.

### 🟡 More observations

**10. CSRF auto-injection works correctly**
base.html JS injects hidden `csrf_token` fields into all forms on page load.
DELETE forms receive CSRF protection via method override + auto-injected field.

**11. mobile_card — access code cooldown reuse**
Reuses recent access codes within cooldown window. Good UX for double-taps.

### 🔴 Infrastructure bugs

**12. smtp.py — unhandled SMTP exceptions**
`_send_via_smtp` doesn't catch `smtplib.SMTPException` or `OSError`. If SMTP server
is unreachable, any email-sending operation fails with 500. Affects:
mobile_card access codes, volunteer application invites, admin account onboarding.
No retry logic.

### 🟡 Infrastructure observations

**13. storage/service.py — Azure vs Supabase routing**
Photo upload uses `_blob_service_client is not None` to decide Azure vs Supabase.
If Azure is removed from config after photos are uploaded, remove_photo would try
wrong backend. Edge case, unlikely in production.

**14. storage/service.py — sync httpx client**
Uses sync `httpx.Client` with `to_thread` for all Supabase operations. Acceptable
but blocks thread pool threads. Could use `httpx.AsyncClient` for native async.

### 🟡 Final observations

**15. semester_transfer.py — extends SqlAlchemyRepository directly**
Inconsistent with rest of codebase where services use composition (have a
`repository` field). Manages its own DB sessions. Minor style issue.

**16. spotify/now_playing.py — proper cleanup chain**
Has `aclose()` with `_owns_client` guard. SQLAlchemyError handling in all DB ops.
Clean shutdown path.

### 📋 Summary

**4 bugs found (all < MEDIUM severity):**
1. login_service — unhandled NotConfiguredError → 500
2. login_service — legacy migration has no rollback (→ user wants to remove legacy)
3. mobile_card — rate limit TOCTOU race in create_session
4. smtp.py — unhandled SMTP exceptions → 500 on email failures

**Architecture assessment: Generally solid.**
- DI container is clean and testable
- CSRF auto-injection protects all forms
- Upload rollback patterns are correct
- Storage cleanup is best-effort (acceptable)
- Auth layer has proper session caching with expiry checks
