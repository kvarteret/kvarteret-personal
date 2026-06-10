from __future__ import annotations

from typing import Any

from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import current_session


class SqlAlchemyRepository:
    """Base for repositories that run inside the request-scoped session.

    One ``AsyncSession`` exists per HTTP request (opened by the request
    session middleware) or per ``session_scope()`` block for scripts.
    Repositories never open sessions or commit; the unit of work commits
    at the request boundary, or explicitly via ``commit_request_session()``
    before external side effects run.
    """

    @property
    def session(self) -> AsyncSession:
        s = current_session()
        if s is not None:
            return s
        raise RuntimeError(
            "No active request-scoped session. HTTP requests get one from "
            "the request session middleware; scripts must wrap calls in "
            "session_scope()."
        )

    async def fetch_all_mappings(self, stmt) -> list[dict[str, Any]]:
        rows = (await self.session.execute(stmt)).mappings().all()
        return [_mapping_to_dict(row) for row in rows]

    async def fetch_first_mapping(self, stmt) -> dict[str, Any] | None:
        row = (await self.session.execute(stmt)).mappings().first()
        return dict(row) if row is not None else None

    async def fetch_one_mapping(self, stmt) -> dict[str, Any]:
        row = (await self.session.execute(stmt)).mappings().one()
        return _mapping_to_dict(row)

    async def execute_one_mapping(self, stmt) -> dict[str, Any]:
        row = (await self.session.execute(stmt)).mappings().one()
        return _mapping_to_dict(row)

    async def fetch_scalars_all(self, stmt) -> list[Any]:
        return list((await self.session.execute(stmt)).scalars().all())

    async def fetch_scalar(self, stmt) -> Any:
        return await self.session.scalar(stmt)

    async def execute(self, stmt, params: Any = None) -> None:
        await self.session.execute(stmt, params)


def _mapping_to_dict(row: RowMapping) -> dict[str, Any]:
    return dict(row)
