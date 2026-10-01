import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.config import Settings
from app.db.session import build_database_runtime, session_scope
from app.domain.event_interest.repository import EventInterestRepository
from app.domain.event_interest.tables import event_interest_clicks

pytestmark = pytest.mark.skipif(
    not os.getenv("EVENT_INTEREST_TEST_DATABASE_URL"),
    reason="Requires disposable PostgreSQL",
)


async def test_click_limit_retry_concurrent_tabs_isolation_and_expiry():
    runtime = build_database_runtime(
        Settings(database_url=os.environ["EVENT_INTEREST_TEST_DATABASE_URL"])
    )
    event = "test-" + uuid4().hex
    repo = EventInterestRepository()
    try:
        async with runtime.engine.begin() as connection:
            await connection.run_sync(
                lambda conn: event_interest_clicks.create(conn, checkfirst=True)
            )

        async def save(source, clicks, batch=None):
            async with session_scope(runtime):
                return await repo.save(
                    event, source * 64, clicks, batch or str(uuid4())
                )

        first = str(uuid4())
        assert await save("a", 5, first) == {"taps": 5, "count": 5}
        assert await save("a", 5, first) == {"taps": 5, "count": 5}
        assert await save("b", 7) == {"taps": 7, "count": 12}
        # Concurrent tabs cannot exceed the shared full-heart limit; retry counts once.
        shared = str(uuid4())
        await asyncio.gather(
            save("a", 8), save("a", 4), save("c", 12, shared), save("c", 12, shared)
        )
        async with session_scope(runtime):
            assert await repo.read(event, "a" * 64) == {"taps": 12, "count": 31}
            assert await repo.read(event, None) == {"taps": 0, "count": 31}
            assert await repo.read(event + "-other", "a" * 64) == {
                "taps": 0,
                "count": 0,
            }
        assert await save("a", 1000) == {"taps": 12, "count": 31}
        async with session_scope(runtime) as session:
            await session.execute(
                text(
                    "UPDATE public.event_interest_clicks SET expires_at = now() - interval '1 day' WHERE event_id = :event AND source_hash = :source"
                ),
                {"event": event, "source": "b" * 64},
            )
        async with session_scope(runtime):
            assert await repo.read(event, "b" * 64) == {"taps": 0, "count": 24}
        assert await save("b", 1) == {"taps": 1, "count": 25}
    finally:
        async with session_scope(runtime) as session:
            await session.execute(
                text(
                    "DELETE FROM public.event_interest_clicks WHERE event_id = :event"
                ),
                {"event": event},
            )
        await runtime.aclose()
