## Architecture Review & Bug Hunt — kvarteret-personal

### Review checklist — ALL DONE ✅

**Layer 1: DI Container (`runtime.py`)**
- [x] Traced all 16 services + 5 infrastructure deps — clean, no circular dependencies
- [x] aclose() cleanup order verified

**Layer 2: Auth (`auth/`)**
- [x] Session store: cache expiry check correct, BadSignature handled
- [x] Cookies: URLSafeSerializer, CSRF auto-injected via JS
- [x] Legacy passwords: timing-safe comparison, proper PBKDF2

**Layer 3: Domain services (`domain/`)**
- [x] volunteers — upload rollback correct, delete order correct
- [x] events — pagination 3x fetch with None-filtering
- [x] mobile_card — rate limit fixed, SMTP error now caught
- [x] volunteer_applications — refactored for complexity
- [x] feedback — uses urllib with to_thread, clean
- [x] spotify — proper aclose() with ownership guard
- [x] semester_transfer — extends SqlAlchemyRepository (minor style issue)

**Layer 4: Infrastructure (`infrastructure/`)**
- [x] storage — Azure + Supabase split, sync httpx client
- [x] email — SMTP exceptions now caught with SmtpDeliveryError
- [x] media — path traversal prevented via Path(filename).name

**Layer 5: Web/API routes**
- [x] All volunteer routes require require_management_user
- [x] E-41: delete confirmation moved to button onclick
- [x] E-49: application dates in template

### Bugs fixed
- [x] Bug #3: mobile_card rate limit TOCTOU → increment before validation
- [x] Bug #4: SMTP exceptions → SmtpDeliveryError + caller handling

### Next: Remove legacy auth
- [ ] Remove legacy_passwords.py
- [ ] Simplify login_service.py (remove legacy migration path)
- [ ] Clean up auth/repository.py (remove legacy methods)
