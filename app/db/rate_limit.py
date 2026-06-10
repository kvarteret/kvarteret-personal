"""Database-backed rate limiting.

Replaces in-process ``TTLCache`` counters with durable Postgres
operations so rate limits survive Vercel instance recycling.

Usage::

    limiter = PostgresRateLimiter(session_factory)
    await limiter.check("login:user@example.com", limit=5, window_seconds=300)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import BigInteger, Column, DateTime, String, Table, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.metadata import public_metadata

rate_limits = Table(
    "rate_limits",
    public_metadata,
    Column("key", String(256), primary_key=True),
    Column("last_used", DateTime(timezone=True), nullable=False),
    Column("count", BigInteger, nullable=False, default=0),
)


class RateLimitExceeded(Exception):
    pass


@dataclass(slots=True)
class PostgresRateLimiter:
    _session_factory: async_sessionmaker[AsyncSession]

    async def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> None:
        """Check and increment the rate limit counter for *key*.

        Counts are scoped to the last *window_seconds*.  Raises
        ``RateLimitExceeded`` if the count exceeds *limit*.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)

        async with self._session_factory() as session:
            async with session.begin():
                # Delete stale entries.
                await session.execute(
                    delete(rate_limits).where(rate_limits.c.last_used < cutoff)
                )

                # Atomically upsert the row for this key.
                # If the row doesn't exist or is stale, reset count to 1.
                # Otherwise increment.
                await session.execute(
                    """INSERT INTO rate_limits (key, last_used, count)
                       VALUES (:key, :now, 1)
                       ON CONFLICT (key) DO UPDATE SET
                           last_used = CASE
                               WHEN rate_limits.last_used < :cutoff THEN :now
                               ELSE rate_limits.last_used
                           END,
                           count = CASE
                               WHEN rate_limits.last_used < :cutoff THEN 1
                               ELSE rate_limits.count + 1
                           END""",
                    {"key": key, "now": now, "cutoff": cutoff},
                )

                # Read current count.
                result = await session.execute(
                    select(rate_limits.c.count).where(rate_limits.c.key == key)
                )
                row = result.first()
                current = row[0] if row else 0

        if current > limit:
            raise RateLimitExceeded(
                f"Rate limit exceeded for '{key}' ({current}/{limit})"
            )
