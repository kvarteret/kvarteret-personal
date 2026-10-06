"""Rebuild aggregate counts before PostHog's full-refresh sync."""

import asyncio

from app.config import Settings
from app.db.session import build_database_runtime, session_scope
from app.warehouse_counts import refresh_counts


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
