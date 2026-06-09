from __future__ import annotations

import pytest

from app.events import SimpleEventBus


@pytest.mark.asyncio
async def test_emit_calls_registered_handler() -> None:
    bus = SimpleEventBus()
    received: list[object] = []

    async def handler(event: object) -> None:
        received.append(event)

    bus.subscribe(str, handler)
    bus.subscribe(str, handler)
    await bus.emit("hello")

    assert len(received) == 2
    assert received == ["hello", "hello"]


@pytest.mark.asyncio
async def test_emit_does_not_call_unregistered_handler() -> None:
    bus = SimpleEventBus()
    received: list[object] = []

    async def handler(event: object) -> None:
        received.append(event)

    bus.subscribe(int, handler)
    await bus.emit("hello")

    assert len(received) == 0


@pytest.mark.asyncio
async def test_multiple_event_types() -> None:
    bus = SimpleEventBus()
    strings: list[str] = []
    ints: list[int] = []

    async def string_handler(event: str) -> None:
        strings.append(event)

    async def int_handler(event: int) -> None:
        ints.append(event)

    bus.subscribe(str, string_handler)
    bus.subscribe(int, int_handler)

    await bus.emit("hello")
    await bus.emit(42)

    assert strings == ["hello"]
    assert ints == [42]


@pytest.mark.asyncio
async def test_event_with_no_handlers_does_not_crash() -> None:
    bus = SimpleEventBus()
    await bus.emit("unhandled")
