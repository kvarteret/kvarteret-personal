## DDD Analysis — kvarteret-personal

### Most complicated modules (by size + method count)

| Module | Lines | Methods | Infra Deps | Complexity Driver |
|---|---|---|---|---|
| **volunteer_applications** | 1013 | 71 | 9 | Multi-step workflow: invite→submit→approve/decline. Group registrations, friend invites, email notifications, photo upload. |
| **groups** | 1018 | 44 | 7 | God service: CRUD + stats + retention + org hierarchy + member counts + role assignments |
| **volunteers** | 889 | 46 | 13 | Central aggregate: profile, roles, courses, photos, relations, search, caching |

### DDD Assessment

**🟢 Ubiquitous language — strong.** Method names use real domain terms:
`create_public_prospect_registration`, `mark_trial_shift_attended`,
`approve_volunteer_application`. Norwegian where appropriate. The code
reads like a staff manual.

**🟢 Bounded contexts — naturally isolated.** All 10 domain modules have
zero cross-references. Each is its own context. No import ever crosses
from one domain module to another. The DI container is the only
integration point.

**🔴 No aggregate roots.** Any service can modify any table. `volunteers`
service modifies `personal`, `personal_bilde`, `verv`, and `historie`.
`groups` service modifies `grupper`, `verv`, `historie`, `grupper_admin_kobling`.
No invariant enforcement across these tables.

**🔴 No domain event model.** `approve_volunteer_application` still runs as an
explicit workflow operation instead of a DDD aggregate event. Side effects are
now separated behind a port, but the module deliberately remains workflow-led
rather than event-led.

**🟡 God services.** `GroupsService` does CRUD, stats, retention analysis,
role management, history management. In DDD this would be split into:
`GroupAggregate` (CRUD), `GroupAnalytics` (read model), `RoleAssignment`
(sub-aggregate).

**🟡 No value objects.** `birth_date`, `phone`, `email` are plain strings.
No `PhoneNumber` value object with validation. No `Semester` value object
(despite heavy semester logic). No `TrialShift` value object for the
application workflow state machine.

### If this were DDD, the volunteer_applications module would look like:

```
ApplicationProcess (aggregate root)
  ├── submit()
  ├── markTrialShiftAttended()
  ├── approve()
  ├── decline()
  └── events:
      ├── ApplicantSubmitted → email handler
      ├── TrialShiftCompleted → notification handler
      └── ApplicantPromoted → profile email handler

GroupRegistration (sub-aggregate)
  ├── inviteFriend()
  └── checkAllSubmitted()

Value Objects:
  ├── PhoneNumber
  ├── PostalCode
  ├── BirthDate
  └── TrialShift (attended: bool, date: Date)
```

### Should you refactor to DDD?

**No, for the same reasons as Clean Architecture.** The current design
is a Transaction Script pattern — each method is a self-contained
business operation. It's simple to understand, easy to debug, and
works for a CRUD-heavy internal tool. DDD adds ceremony (events,
aggregates, value objects) that would slow down a 1-2 person team
without commensurate benefit.
