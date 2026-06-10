"""Rate limiting backed by Postgres so limits survive serverless instances.

In-process counters do not work on Vercel: each function instance keeps its
own counts, so concurrent instances multiply the effective limit and instance
recycling resets it. Postgres is the only shared state this app has, and at
this traffic the extra query per guarded request is irrelevant.

Counting uses a fixed window anchored at the first hit: the counter resets
once the row is older than the window. ``hit`` increments before checking,
so callers that validate credentials after calling ``hit`` are TOCTOU-safe.

``InMemoryRateLimiter`` exists for unit tests and offline tooling only —
never wire it in production.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import BigInteger, Column, DateTime, String, Table, delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.metadata import public_metadata

rate_limits = Table(
    "rate_limits",
    public_metadata,
    Column("key", String(256), primary_key=True),
    Column("last_used", DateTime(timezone=True), nullable=False),
    Column("count", BigInteger, nullable=False, default=0),
)

# Rows older than this are garbage regardless of any caller's window
# (the longest window in use is minutes). Cleaned up opportunistically.
_STALE_ROW_MAX_AGE = timedelta(days=1)

_UPSERT_AND_COUNT = text(
    """
    INSERT INTO rate_limits (key, last_used, count)
    VALUES (:key, :now, 1)
    ON CONFLICT (key) DO UPDATE SET
        last_used = CASE
            WHEN rate_limits.last_used < :cutoff THEN :now
            ELSE rate_limits.last_used
        END,
        count = CASE
            WHEN rate_limits.last_used < :cutoff THEN 1
            ELSE rate_limits.count + 1
        END
    RETURNING count
    """
)


class RateLimitExceeded(Exception):
    pass


class RateLimiter(Protocol):
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> None:
        """Count one attempt for *key*; raise ``RateLimitExceeded`` past *limit*."""
        ...

    async def clear(self, *keys: str) -> None:
        """Reset the counters for *keys* (e.g. after a successful login)."""
        ...


@dataclass(slots=True)
class PostgresRateLimiter:
    session_factory: async_sessionmaker[AsyncSession]

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)

        async with self.session_factory() as session:
            async with session.begin():
                # Opportunistic cleanup. Deliberately uses a fixed long age,
                # not this call's cutoff: deleting by the caller's window
                # would reset counters of keys with longer windows.
                await session.execute(
                    delete(rate_limits).where(
                        rate_limits.c.last_used < now - _STALE_ROW_MAX_AGE
                    )
                )
                result = await session.execute(
                    _UPSERT_AND_COUNT,
                    {"key": key, "now": now, "cutoff": cutoff},
                )
                current = result.scalar_one()

        if current > limit:
            raise RateLimitExceeded(
                f"Rate limit exceeded for '{key}' ({current}/{limit})"
            )

    async def clear(self, *keys: str) -> None:
        if not keys:
            return
        async with self.session_factory() as session:
            async with session.begin():
                await session.execute(
                    delete(rate_limits).where(rate_limits.c.key.in_(keys))
                )


@dataclass(slots=True)
class InMemoryRateLimiter:
    """Test double with the same fixed-window semantics. Not for production."""

    _counters: dict[str, tuple[float, int]] = field(default_factory=dict)

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        window_start, count = self._counters.get(key, (now, 0))
        if now - window_start >= window_seconds:
            window_start, count = now, 0
        count += 1
        self._counters[key] = (window_start, count)
        if count > limit:
            raise RateLimitExceeded(
                f"Rate limit exceeded for '{key}' ({count}/{limit})"
            )

    async def clear(self, *keys: str) -> None:
        for key in keys:
            self._counters.pop(key, None)
