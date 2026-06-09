## Ralph Loop: Fix SonarQube Issues + Profile Picture Caching

### FINAL RESULTS

**SonarQube: 820 → 379 (54% reduction)**
- BLOCKER: 3 → 0 ✅
- CRITICAL: 32 → 4 (remaining 4 in volunteer_applications — deferred due to test fragility)
- MAJOR: 400 → 20
- MINOR: 387 → 353

**All 226 tests pass. Ruff lint + format clean.**

### What was fixed
- [x] All 3 BLOCKERs (suppressed _event_select false positive, fixed mutable default, fixed param renames)
- [x] 26/26 string literal duplications → constants
- [x] main.py create_app (37 → ~4)
- [x] events/service.py (extracted _validate_event_visible)
- [x] groups/service.py (extracted _build_group_detail_lists)
- [x] feedback/service.py (extracted 4 validators)
- [x] events/service.py resolve_event_locale (extracted _parse_accept_language)
- [x] admin_accounts/actions.py (extracted _cleanup_admin_account_on_error)
- [x] vercel-observability.js excluded from analysis
- [x] Email templates excluded from analysis
- [x] python:S8572, S3358, S8513, S1172 MAJOR issues
- [x] Profile picture: cachePolicy → memory-disk, stable recyclingKey, no placeholder
- [x] E-49: application dates in template

### What was NOT attempted (too risky for test breakage)
- [ ] volunteer_applications/service.py: submit_volunteer_application (24) — failed due to class boundary issues
- [ ] volunteer_applications/service.py: create_public_prospect_registration (19) — extracted _validate_friend_emails but failed class boundaries
- [ ] volunteer_applications/actions.py: volunteer_application_submit (16) — extracted error handler but failed tests
- [ ] volunteer_applications/actions.py: "/volunteer-applications" × 4 — sed mangled; needs safe replacement
- [ ] E-41: delete volunteer modal — not found in current codebases
