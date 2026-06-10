# ADR-001: Pragmatic Modular Monolith with Explicit Workflows

**Status:** Accepted
**Date:** 2026-06-09
**Updated:** 2026-06-10
**Deciders:** E-Tjenesten

## Context

`kvarteret-personal` is a FastAPI modular monolith. Routes delegate to domain
services, services use SQLAlchemy Core repositories, and `app/runtime.py` wires
the object graph.

The main architecture problem is not lack of infrastructure. The problem is
that stateful workflows are hard to trace when one large service mixes:

- state transitions
- validation
- SQL persistence
- photo handling
- cache invalidation
- email delivery
- cleanup

The clearest example is volunteer applications. The lifecycle is:

```text
invite -> submit -> mark trial shift -> approve/decline
```

That lifecycle should be readable from one file.

## Decision

Adopt a pragmatic modular-monolith style organized around explicit workflows for
stateful business processes.

For workflow-heavy modules:

- add a `workflow.py` coordinator whose methods read like the business process
- keep routes responsible for HTTP/form parsing
- keep repositories responsible for SQL
- keep side effects behind named methods such as `after_submitted` and
  `after_approved`
- avoid putting core approval rules or state transitions behind an event bus

For read-heavy admin modules:

- split query/read-model code out of broad service classes when it reduces
  file size without changing behavior
- keep write methods in the service that owns the mutation

## Current Implementation

`app/domain/volunteer_applications/workflow.py` is the proof point. It
coordinates:

- `invite`
- `register_public_prospect`
- `submit`
- `mark_trial_shift_attended`
- `approve`
- `drop_group_invitee`
- `delete`
- `resend_invitation`

`app/domain/volunteer_applications/side_effects.py` centralizes the current
side effects:

- pending-count cache invalidation
- invitation email
- friend invitation email
- profile completion email
- deleted-application photo cleanup

`VolunteerApplicationsService` remains the route-facing facade for compatibility
with existing route dependencies and tests. Its public methods delegate to the
workflow; the lower-level record/transition methods retain the existing
validation and repository behavior.

## Event Bus Policy

The in-process event bus prototype was removed in June 2026. No runtime
consumers existed and the workflow/side-effects pattern proved sufficient for
all cross-cutting concerns (cache invalidation, email delivery, photo cleanup).

Do not add Celery, Redis queues, Temporal, event sourcing, CQRS, or
microservices for this app unless a concrete reliability requirement appears.

## Cleanup Decisions

Volunteer documents are removed from the active app surface. The app no longer
serves document panels, document routes, signed document media URLs, or document
storage APIs.

Supabase Storage is no longer a media backend for `kvarteret-personal`.
Personnel photos use Azure Blob Storage through `StorageService`. Supabase
continues to provide Postgres and Auth for this app.

## Consequences

Positive:

- The volunteer application lifecycle is traceable from one coordinator.
- Side effects have names and tests instead of being scattered through long
  service methods.
- Routes and public behavior stay stable while internals become easier to
  navigate.
- Removing documents and Supabase media fallback reduces active infrastructure
  surface area.
- Group admin read/statistics SQL now lives in `groups/queries.py`, keeping
  `groups/service.py` focused on writes and delete guards.

Negative:

- There is one more internal module to follow from the service facade.
- The service still contains many data classes and operation methods; this ADR
  does not attempt a full domain-model rewrite.

## Follow-up

- Extract volunteer role assignments into their own domain module after the
  document cleanup settles.
- Keep future refactors staged and behavior-preserving unless a product change
  requires otherwise.
