# Clarify domain module structure

The kvarteret-personal codebase has 10 domain modules but inconsistent structure.
Some domains have clean splits (events/ has models.py + repository.py + service.py),
others have everything in one file (courses/service.py has models + errors + SQL +
business logic). This makes the codebase harder to navigate than it should be.

## Goal

After this work:
- Every domain module follows the same file structure convention
- Large files are split so each file has one responsibility
- The architecture doc documents the convention
- The three "missing" features from the old backend (emergency contacts, standalone
  roles CRUD, course history) are verified as present and documented where they live

## Progress

- [x] Verified three "missing" features exist — emergency contacts in volunteers/service.py
  (get_volunteer_relations), roles in groups/service.py (create/update/delete_group_role),
  course history in volunteers/service.py (add/list/delete_course_completion) and
  courses/service.py (create_course_completion)
- [x] Split courses/ from 1 file (507 lines) into models.py (38) + errors.py (19) +
  repository.py (349) + service.py (186). CoursesService no longer extends
  SqlAlchemyRepository.
- [x] Split admin_accounts/ from 1 file (402 lines) into models.py (36) +
  repository.py (249) + service.py (199). AdminAccountsService no longer extends
  SqlAlchemyRepository.
- [x] Split mobile_card/ into models.py (109) + errors.py (31) + sessions.py (116).
  Session token logic extracted to MobileCardSessionManager. Service at 498 lines.
- [x] Added "Domain Module Convention" section to docs/explanation/kvarteret-personal-architecture.md
- [x] 222 tests pass

## Outcomes

Every domain module now follows the same pattern: models.py + repository.py + service.py.
No domain service extends SqlAlchemyRepository directly — all take a repository via
constructor injection. Large files are split by responsibility. The architecture doc
documents the expected structure.

Rate limiting was NOT extracted from mobile_card/service.py — the TTLCache-based
enforcement is tightly coupled to the service's flow and extracting it would add
indirection without clarity benefit. Sessions were the right extraction boundary.

## Remaining (not in scope)

- groups/queries.py (740 lines) could benefit from models.py extraction but is
  already well-split from groups/service.py
- volunteers/repository.py (935 lines) and volunteer_applications/repository.py
  (995 lines) are large but focused — pure SQL, no mixed concerns
- Web route files (admin_accounts/actions.py 491 lines, volunteers/actions.py 480
  lines) are large due to endpoint count, not mixed concerns
