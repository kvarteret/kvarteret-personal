"""Rebuild aggregate counts before PostHog's full-refresh sync."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.session import build_database_runtime, session_scope

REFRESH_SQL = """
INSERT INTO public.warehouse_volunteer_counts
    (semester, scope_key, group_id, volunteer_count, is_suppressed, refreshed_at)
SELECT semester,
       CASE WHEN GROUPING(group_id) = 1 THEN 'organisation'
            ELSE 'group:' || group_id::text END,
       CASE WHEN GROUPING(group_id) = 1 THEN NULL ELSE group_id END,
       CASE WHEN GROUPING(group_id) = 0 AND COUNT(DISTINCT volunteer_id) < 5
            THEN NULL ELSE COUNT(DISTINCT volunteer_id) END,
       GROUPING(group_id) = 0 AND COUNT(DISTINCT volunteer_id) < 5,
       CURRENT_TIMESTAMP
FROM public.role_assignments
GROUP BY GROUPING SETS ((semester), (semester, group_id))
"""


async def refresh_counts(session: AsyncSession) -> int:
    # Serialize refreshers. DELETE + INSERT share the caller's transaction;
    # readers see the previous complete export until the replacement commits.
    await session.execute(
        text("LOCK TABLE public.warehouse_volunteer_counts IN EXCLUSIVE MODE")
    )
    await session.execute(text("DELETE FROM public.warehouse_volunteer_counts"))
    result = await session.execute(text(REFRESH_SQL))
    return result.rowcount


async def main() -> None:
    runtime = build_database_runtime(Settings())
    try:
        async with session_scope(runtime) as session:
            count = await refresh_counts(session)
        print(f"Refreshed {count} aggregate volunteer-count rows")
    finally:
        await runtime.aclose()


if __name__ == "__main__":
    asyncio.run(main())
