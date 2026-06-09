## Phase 1: Event Bus + volunteer_applications migration — DONE

### 1.1 Create `app/events.py` ✅
### 1.2 Wire into runtime.py ✅
### 1.3 Create volunteer_applications events ✅
### 1.4 Extract side effects ✅ (coexistence: both inline + handler)
### 1.5 Register handlers in runtime.py ✅
### 1.6 All 223 tests pass ✅

Coexistence strategy: cache invalidation runs both inline (in _save_and_cleanup_photos)
AND via the ApplicationSubmitted event handler. No regression risk. In Phase 2
we'll remove the inline call once we have handler test coverage.

### Next phases
- Phase 2: Move _invalidate_pending_count_cache fully to handler + add tests
- Phase 3: ApplicationApproved handler for profile completion emails
- Phase 4: mobile_card access code email handler
- Phase 5: admin_accounts onboarding email handler
