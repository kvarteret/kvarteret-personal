import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.config import Settings
from app.db.session import build_database_runtime, session_scope
from app.domain.event_interest.repository import EventInterestRepository
from app.domain.event_interest.tables import event_interest

pytestmark = pytest.mark.skipif(
    not os.getenv("EVENT_INTEREST_TEST_DATABASE_URL"),
    reason="Requires disposable PostgreSQL",
)


async def test_coalescing_concurrency_isolation_removal_and_expiry():
    runtime = build_database_runtime(
        Settings(database_url=os.environ["EVENT_INTEREST_TEST_DATABASE_URL"])
    )
    event = "test-" + uuid4().hex
    repo = EventInterestRepository()
    try:
        async with runtime.engine.begin() as connection:
            await connection.run_sync(
                lambda conn: event_interest.create(conn, checkfirst=True)
            )

        async def save(source, taps):
            async with session_scope(runtime):
                return await repo.save(event, source * 64, taps)

        assert await save("a", 1) == {"taps": 1, "score": 0.25}
        assert await save("a", 4) == {"taps": 4, "score": 0.75}
        assert await save("a", 1) == {"taps": 4, "score": 0.75}
        await asyncio.gather(save("a", 8), save("b", 4), save("c", 12))
        async with session_scope(runtime):
            assert await repo.read(event, "a" * 64) == {"taps": 8, "score": 2.75}
            assert await repo.read(event + "-other", "a" * 64) == {
                "taps": 0,
                "score": 0,
            }
        assert await save("a", 0) == {"taps": 0, "score": 1.75}
        async with session_scope(runtime) as session:
            await session.execute(
                text(
                    "UPDATE public.event_interest SET expires_at = now() - interval '1 day' WHERE event_id = :event AND source_hash = :source"
                ),
                {"event": event, "source": "b" * 64},
            )
        async with session_scope(runtime):
            assert await repo.read(event, "b" * 64) == {"taps": 0, "score": 1}
        assert await save("b", 1) == {"taps": 1, "score": 1.25}
    finally:
        async with session_scope(runtime) as session:
            await session.execute(
                text("DELETE FROM public.event_interest WHERE event_id = :event"),
                {"event": event},
            )
        await runtime.aclose()
