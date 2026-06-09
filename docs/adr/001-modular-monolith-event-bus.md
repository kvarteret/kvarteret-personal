# ADR-001: Adopt Modular Monolith with Lightweight Event Bus

**Status:** Proposed
**Date:** 2026-06-09
**Deciders:** E-Tjenesten

## Inspiration: PostHog

PostHog runs a 100k+ line Django monolith with 50+ engineers and actively argues
against microservices. Their stack mirrors ours in key ways:

| PostHog | Us |
|---|---|
| Django monolith | FastAPI monolith |
| Celery (email, quick async) | SimpleEventBus (in-process) |
| Temporal (mission-critical workflows) | Future if needed |
| ClickHouse + PostgreSQL | PostgreSQL |
| Feature flags for rollout | Coexistence during migration |

PostHog's task worker decision tree maps directly to our event bus scope:

> *"Is it a tiny, low-latency, fire-and-forget task (e.g. send email)? → Celery"*
> *"Is it mission-critical with complex failure scenarios? → Temporal"*

Our event bus is the in-process equivalent of Celery for tiny tasks.
If we ever need exactly-once guarantees, retry policies, or long-running
workflows, we'd add Temporal — not build it ourselves.

## Context

The kvarteret-personal codebase is a FastAPI application with 10 domain
modules. Each module is naturally isolated (zero cross-imports between
domain modules) and wired through a single DI container in `runtime.py`.
The application follows a Transaction Script pattern: each service method
performs a complete business operation from start to finish, including
side effects like cache invalidation, email delivery, and audit logging.

This approach works but creates two problems:

1. **Service methods have too many responsibilities.** A single method like
   `submit_volunteer_application` handles validation, photo processing, DB
   persistence, cache invalidation, and email notification. This makes
   methods long and hard to test in isolation.

2. **Cross-cutting concerns are duplicated.** Every method that creates or
   modifies data manually calls `_invalidate_pending_count_cache()`,
   `log_admin_activity()`, or `email_sender.send_email()`. There is no
   central place to add a new cross-cutting concern.

## Decision

We will adopt a **Modular Monolith** architecture with a lightweight
in-process event bus, inspired by PostHog's approach:

> *"A well-structured monolith with clear boundaries is preferable to a
> poorly-structured set of microservices."*

### What changes

1. **New module: `app/events.py`** — A `SimpleEventBus` (~30 lines) with
   `emit(event)` and `subscribe(event_type, handler)`. Handlers are async
   callables registered at startup. In-process delivery (same event loop).
   Equivalent to PostHog's "Celery for tiny tasks" — no persistence,
   no retry, no external queues.

2. **Domain events as dataclasses** — Each module defines its events in
   `domain/<module>/events.py`. Events are plain `@dataclass` objects.
   No base class required, no serialization (in-process only).

3. **Service methods publish, handlers subscribe** — Core business logic
   stays in service methods. Side effects move to standalone handler
   functions registered at startup.

4. **Handlers registered in `runtime.py`** — The DI container wires
   handlers at startup, injecting dependencies into handler functions.

### What does NOT change

- Domain modules remain isolated (no cross-imports)
- DI container remains the central wiring point
- Database access pattern stays the same
- Route handlers continue delegating to services
- No event sourcing, no CQRS, no eventual consistency
- No Celery, Redis, Temporal, or external queues (until needed)

### Event bus contract

```python
# app/events.py

EventHandler = Callable[[Any], Coroutine[Any, Any, None]]

class SimpleEventBus:
    def __init__(self):
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def emit(self, event: object) -> None:
        for handler in self._handlers.get(type(event), []):
            await handler(event)
```

## Consequences

**Positive:**
- Service methods shorter, focused on core business logic
- Cross-cutting concerns centralized in handler functions
- Handlers independently testable with mock events
- New side effects added without modifying service code

**Negative:**
- Indirection: must trace from service → events → handlers
- Fire-and-forget: if a handler fails after DB commit, side effect is lost.
  For critical email delivery, this is acceptable (email is best-effort).
  If we later need guarantee, we'd add an outbox pattern or Temporal —
  not build it ourselves.

## Migration Plan

Each phase is independently deployable — old code and new event-driven
code coexist during migration (PostHog-style feature flags optional).

- **Phase 1:** `SimpleEventBus` + `volunteer_applications` (cache invalidation)
- **Phase 2:** `volunteers` module (photo updates, cache invalidation)
- **Phase 3:** `mobile_card` module (access code emails)
- **Phase 4:** `admin_accounts` module (onboarding emails)
- **Future:** If we need retry/guarantee → Temporal (not Celery, per
  PostHog's cost analysis: Temporal is ~300x cheaper per operation)
