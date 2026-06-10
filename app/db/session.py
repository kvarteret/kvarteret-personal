from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
import os
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
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
        raise NotConfiguredError(
            "DATABASE_URL is required for database-backed features."
        )

    connect_args: dict[str, object] = {}
    is_sqlite = settings.database_url.startswith("sqlite+aiosqlite")
    if is_sqlite:
        connect_args["check_same_thread"] = False

    engine_kwargs: dict[str, object] = {
        "connect_args": connect_args,
        "pool_pre_ping": True,
    }
    if not is_sqlite:
        # Serverless workers should not retain sticky DB sessions.
        use_null_pool = settings.database_use_null_pool or bool(os.getenv("VERCEL"))
        if use_null_pool:
            engine_kwargs["poolclass"] = NullPool
        else:
            engine_kwargs["pool_size"] = settings.database_pool_size
            engine_kwargs["max_overflow"] = settings.database_max_overflow
            engine_kwargs["pool_timeout"] = settings.database_pool_timeout_seconds
            engine_kwargs["pool_recycle"] = settings.database_pool_recycle_seconds
            engine_kwargs["pool_use_lifo"] = True

    engine = create_async_engine(settings.database_url, **engine_kwargs)
    return DatabaseRuntime(
        engine=engine,
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )


# ── Request-scoped session plumbing ──────────────────────────────

_request_session_ctx: ContextVar[AsyncSession | None] = ContextVar(
    "_request_session", default=None
)


def set_request_session(session: AsyncSession):
    """Bind *session* as the request-scoped session; returns a reset token."""
    return _request_session_ctx.set(session)


def reset_request_session(token) -> None:
    _request_session_ctx.reset(token)


def current_session() -> AsyncSession | None:
    """Return the request-scoped session if one is active, else None."""
    return _request_session_ctx.get()


async def commit_request_session() -> None:
    """Commit the request-scoped unit of work now.

    Workflow coordinators call this before firing external side effects
    (email, future SMS) so the commit-before-effect ordering holds: an
    effect must never announce a state change the database can still
    roll back. Statements executed afterwards start a new transaction
    on the same session, committed at the request boundary as usual.
    """
    session = current_session()
    if session is not None and session.in_transaction():
        await session.commit()


@asynccontextmanager
async def session_scope(
    runtime: DatabaseRuntime,
) -> AsyncIterator[AsyncSession]:
    """Context manager for scripts and background callers.

    Yields a single AsyncSession, commits on success, rolls back on
    exception, and sets the ContextVar so repositories can find it.
    """
    async with runtime.session_factory() as session:
        token = _request_session_ctx.set(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            _request_session_ctx.reset(token)


async def get_request_session(
    runtime: DatabaseRuntime,
) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — one ``AsyncSession`` per HTTP request.

    Sets the session on a ``ContextVar`` so that any repository
    constructed during the request can find it without being
    explicitly passed a session.
    """
    async with runtime.session_factory() as session:
        token = _request_session_ctx.set(session)
        try:
            yield session
        finally:
            _request_session_ctx.reset(token)
