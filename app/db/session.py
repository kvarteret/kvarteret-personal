from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.errors import NotConfiguredError


@dataclass(slots=True)
class DatabaseRuntime:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def aclose(self) -> None:
        await self.engine.dispose()


class DatabaseRuntimeManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._runtime: DatabaseRuntime | None = None

    def get_runtime(self) -> DatabaseRuntime:
        if self._runtime is None:
            self._runtime = build_database_runtime(self.settings)
        return self._runtime

    def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self.get_runtime().session_factory

    async def aclose(self) -> None:
        if self._runtime is None:
            return
        runtime = self._runtime
        self._runtime = None
        await runtime.aclose()


def build_database_runtime(settings: Settings) -> DatabaseRuntime:
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
