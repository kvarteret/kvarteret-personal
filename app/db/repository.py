from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import current_session


class SqlAlchemyRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            raise RuntimeError(
                "A session factory must be configured before using this repository."
            )
        return self._session_factory

    @property
    def session(self) -> AsyncSession:
        """Return the active request-scoped session if available.

        Raises RuntimeError outside of a request scope — use
        ``self.session_factory`` for explicit session management.
        """
        s = current_session()
        if s is not None:
            return s
        raise RuntimeError(
            "No active request-scoped session. Use session_factory() "
            "or wrap the call in session_scope()."
        )

    async def fetch_all_mappings(self, stmt) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [_mapping_to_dict(row) for row in rows]

    async def fetch_first_mapping(self, stmt) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            row = (await session.execute(stmt)).mappings().first()
        return dict(row) if row is not None else None

    async def fetch_one_mapping(self, stmt) -> dict[str, Any]:
        async with self.session_factory() as session:
            row = (await session.execute(stmt)).mappings().one()
        return _mapping_to_dict(row)

    async def execute_one_mapping(self, stmt) -> dict[str, Any]:
        async with self.session_factory.begin() as session:
            row = (await session.execute(stmt)).mappings().one()
        return _mapping_to_dict(row)

    async def fetch_scalars_all(self, stmt) -> list[Any]:
        async with self.session_factory() as session:
            return list((await session.execute(stmt)).scalars().all())

    async def fetch_scalar(self, stmt) -> Any:
        async with self.session_factory() as session:
            return await session.scalar(stmt)

    async def execute(self, stmt, params: Any = None) -> None:
        async with self.session_factory() as session:
            await session.execute(stmt, params)
            await session.commit()

    async def execute_in_transaction(
        self,
        callback: Callable[[AsyncSession], Awaitable[Any]],
    ) -> Any:
        async with self.session_factory.begin() as session:
            return await callback(session)


def _mapping_to_dict(row: RowMapping) -> dict[str, Any]:
    return dict(row)
