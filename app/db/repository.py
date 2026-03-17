from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

class SqlAlchemyRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | Callable[[], async_sessionmaker[AsyncSession]] | None = None,
    ) -> None:
        self._session_factory = session_factory

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            raise RuntimeError("A session factory must be configured before using this repository.")
        if callable(self._session_factory):
            return self._session_factory()
        return self._session_factory

    async def fetch_all_mappings(self, stmt) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            return list((await session.execute(stmt)).mappings().all())

    async def fetch_first_mapping(self, stmt) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            row = (await session.execute(stmt)).mappings().first()
        return dict(row) if row is not None else None

    async def fetch_one_mapping(self, stmt) -> dict[str, Any]:
        async with self.session_factory() as session:
            return dict((await session.execute(stmt)).mappings().one())

    async def execute_one_mapping(self, stmt) -> dict[str, Any]:
        async with self.session_factory.begin() as session:
            return dict((await session.execute(stmt)).mappings().one())

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

    async def execute_in_transaction(self, callback):
        async with self.session_factory.begin() as session:
            return await callback(session)
