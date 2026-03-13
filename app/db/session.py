from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.errors import NotConfiguredError


@dataclass(slots=True)
class DatabaseRuntime:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def aclose(self) -> None:
        await self.engine.dispose()


@lru_cache(maxsize=1)
def get_database_runtime() -> DatabaseRuntime:
    settings = get_settings()
    if not settings.database_url:
        raise NotConfiguredError("DATABASE_URL is required for database-backed features.")

    connect_args: dict[str, object] = {}
    is_sqlite = settings.database_url.startswith("sqlite+aiosqlite")
    if is_sqlite:
        connect_args["check_same_thread"] = False

    engine_kwargs: dict[str, object] = {
        "connect_args": connect_args,
        "pool_pre_ping": True,
    }
    if not is_sqlite and (settings.app_env == "production" or os.getenv("VERCEL")):
        engine_kwargs["poolclass"] = NullPool

    engine = create_async_engine(settings.database_url, **engine_kwargs)
    return DatabaseRuntime(
        engine=engine,
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return get_database_runtime().session_factory


async def dispose_database_runtime() -> None:
    if get_database_runtime.cache_info().currsize == 0:
        return
    runtime = get_database_runtime()
    get_database_runtime.cache_clear()
    await runtime.aclose()
