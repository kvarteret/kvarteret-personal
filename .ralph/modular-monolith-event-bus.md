## Modular Monolith Event Bus — Phase 1 COMPLETE ✅

### Delivered
- [x] `app/events.py` — SimpleEventBus (30 lines)
- [x] `app/domain/volunteer_applications/events.py` — 3 domain events
- [x] Wired into `ApplicationContainer` + `runtime.py`
- [x] `submit_volunteer_application` emits `ApplicationSubmitted`
- [x] Handler registered: `_on_application_submitted` (cache invalidation)
- [x] Coexistence: cache invalidated inline AND via handler
- [x] 4 unit tests for SimpleEventBus (all passing)
- [x] ADR-001 written (PostHog-inspired)
- [x] All 227 tests pass, ruff clean

### Architecture
```
submit_volunteer_application()
    → validate + photo + save
    → bus.emit(ApplicationSubmitted)
          → handler: cache.invalidate()
```

### Next phases (deferred)
- Phase 2: `ApplicationApproved` handler (profile completion email)
- Phase 3: `mobile_card` access code email handler
- Phase 4: `admin_accounts` onboarding email handler
- Phase 5: Remove inline cache/email calls (after handler test coverage)
