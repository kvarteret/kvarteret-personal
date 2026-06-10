# Complete M4 through M9 — one commit per milestone

## M4: Retire legacy DigitalInternkort API and auth-bridge vestiges
- [ ] Delete `app/api/legacy/` and its router registration in `app/api/router.py`
- [ ] Remove DigitalInternkort operations from openapi.json (via `make openapi`)
- [ ] Delete legacy-shape tests (grep for DigitalInternkort in tests)
- [ ] Rename `LoginService.login_with_bridge` to `login`
- [ ] Drop `legacy_user_id` from `app/auth/models.py`, `app/auth/repository.py`, `app/domain/admin_accounts/service.py`
- [ ] Migration to drop `auth_migration_events` and `user_accounts.legacy_user_id`
- [ ] `make test`, `make lint`, `make openapi-check` pass

## M5: Data-access overhaul
- [ ] Request-scoped session: middleware/dependency in `app/db/session.py`, share session across request
- [ ] Delete `execute_in_transaction` and per-method commit from `SqlAlchemyRepository`
- [ ] Remove `session_factory()` usage from all repositories — they receive the session
- [ ] Repositories return typed rows (Pydantic/dataclass), delete `mappers.py` except real derivations
- [ ] Replace `Any` in workflow protocols with real types
- [ ] Remove `repository or SomeRepository()` hidden defaults from service constructors
- [ ] Repository Protocol per module + contract test
- [ ] Extract shared keyset pagination helper
- [ ] Replace scattered `perf_counter` with SQLAlchemy event listener
- [ ] `make test`, `make lint`, `make openapi-check` pass

## M6: Modular monolith with owned tables
- [ ] Move table definitions from `app/db/table_defs/public.py` into `app/domain/{owner}/tables.py`
- [ ] Create `mobile_card_access_codes` table, move token columns out of `volunteer_records`
- [ ] Add importlinter contracts: layers, independence, cross-module read edges
- [ ] Extract `app/domain/role_assignments/` from volunteers
- [ ] Split oversized modules along read/write line (volunteers, volunteer_applications)
- [ ] `make lint-imports` green, no domain directory > ~1,200 lines
- [ ] `make test`, `make lint`, `make openapi-check` pass

## M7: Volunteer application state machine
- [ ] Create `app/domain/volunteer_applications/state_machine.py` — pure, I/O-free
- [ ] Define `ApplicationState`, `MembershipState`, `ApplicationAction` enums
- [ ] Explicit transition table + `transition()` function
- [ ] Side effects as named serializable records
- [ ] `domain_events` table migration + audit log insertion
- [ ] Re-wire workflow to use state machine
- [ ] Database check constraints on status column
- [ ] Atomic group approval in one transaction
- [ ] Full state × action test matrix
- [ ] `docs/adr/003-domain-event-log.md`
- [ ] `make test`, `make lint`, `make openapi-check` pass

## M8: Security hardening
- [ ] Security headers middleware (off-the-shelf, not hand-rolled)
- [ ] Database-backed rate limiting (replace TTLCache)
- [ ] Hash mobile-card access codes (slow hash/HMAC)
- [ ] Revocable mobile-card server-side sessions
- [ ] Fix prospect endpoint enumeration leak
- [ ] Sweep error handlers for info leaks
- [ ] Pin auth invariant regression test
- [ ] `make test`, `make lint`, `make openapi-check` pass

## M9: Auth consolidation
- [ ] `app/auth/permissions.py` — Permission enum, roles as bundles, grants table
- [ ] `require_permission` FastAPI dependency
- [ ] Argon2 admin passwords on `user_accounts`
- [ ] Volunteers out of `auth.users`, GoTrue retired
- [ ] `SmsGateway` protocol (no implementation)
- [ ] `docs/adr/002-auth-consolidation.md`
- [ ] `make test`, `make lint`, `make openapi-check` pass
