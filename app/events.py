from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Coroutine

EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


class SimpleEventBus:
    """In-process synchronous event bus.

    Handlers are called in registration order within the same event loop.
    No persistence, no retry, no external queues. For side effects only:
    cache invalidation, email delivery, audit logging.

    Usage:
        bus = SimpleEventBus()
        bus.subscribe(ApplicationSubmitted, on_application_submitted)
        await bus.emit(ApplicationSubmitted(application_id=42))
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        """Register an async handler for an event type.

        Handlers receive the event dataclass instance as their only argument.
        Multiple handlers can subscribe to the same event type; they run in
        registration order.
        """
        self._handlers[event_type].append(handler)

    async def emit(self, event: object) -> None:
        """Deliver an event to all registered handlers.

        Handlers are called sequentially (not concurrently) to avoid
        race conditions. A handler exception stops delivery to remaining
        handlers — wrap individual handlers in try/except if you need
        resilience.
        """
        for handler in self._handlers.get(type(event), []):
            await handler(event)
