"""Run daily with the normal backend environment; deletes expired responses."""

import asyncio

from sqlalchemy import text

from app.config import Settings
from app.db.session import build_database_runtime, session_scope


async def main() -> None:
    runtime = build_database_runtime(Settings())
    try:
        async with session_scope(runtime) as session:
            result = await session.execute(
                text("DELETE FROM public.event_interest WHERE expires_at <= now()")
            )
            print(f"Removed {result.rowcount} expired event responses")
    finally:
        await runtime.aclose()


if __name__ == "__main__":
    asyncio.run(main())
