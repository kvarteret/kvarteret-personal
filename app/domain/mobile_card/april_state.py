from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import TTLCache
from app.db.repository import SqlAlchemyRepository
from app.db.tables import mobile_card_april_state


@dataclass(slots=True)
class MobileCardAprilState:
    enabled: bool
    updated_at: datetime | None = None
    updated_by_user_account_id: int | None = None


class MobileCardAprilStateRepository(SqlAlchemyRepository):
    async def get_state(self) -> MobileCardAprilState:
        row = await self.fetch_first_mapping(
            select(
                mobile_card_april_state.c.enabled,
                mobile_card_april_state.c.updated_at,
                mobile_card_april_state.c.updated_by_user_account_id,
            ).limit(1)
        )
        if row is None:
            return MobileCardAprilState(enabled=False)
        return MobileCardAprilState(
            enabled=bool(row["enabled"]),
            updated_at=row["updated_at"],
            updated_by_user_account_id=row["updated_by_user_account_id"],
        )

    async def set_enabled(
        self, *, enabled: bool, updated_by_user_account_id: int | None
    ) -> None:
        now = datetime.now(UTC)

        async def _write(session: AsyncSession) -> None:
            result = await session.execute(
                update(mobile_card_april_state).values(
                    enabled=enabled,
                    updated_at=now,
                    updated_by_user_account_id=updated_by_user_account_id,
                )
            )
            if (result.rowcount or 0) == 0:
                await session.execute(
                    insert(mobile_card_april_state).values(
                        enabled=enabled,
                        updated_at=now,
                        updated_by_user_account_id=updated_by_user_account_id,
                    )
                )

        await _write(self.session)


class MobileCardAprilStateService:
    def __init__(
        self,
        repository: MobileCardAprilStateRepository,
        cache_ttl_seconds: int = 30,
    ) -> None:
        self.repository = repository
        self._cache: TTLCache[str, MobileCardAprilState] = TTLCache(
            ttl_seconds=cache_ttl_seconds,
            max_entries=1,
        )

    async def get_state(self) -> MobileCardAprilState:
        cached = self._cache.get("state")
        if cached is not None:
            return cached
        state = await self.repository.get_state()
        self._cache.set("state", state)
        return state

    async def is_enabled(self) -> bool:
        return (await self.get_state()).enabled

    async def set_enabled(
        self, *, enabled: bool, updated_by_user_account_id: int | None
    ) -> None:
        await self.repository.set_enabled(
            enabled=enabled,
            updated_by_user_account_id=updated_by_user_account_id,
        )
        self._cache.set(
            "state",
            MobileCardAprilState(
                enabled=enabled,
                updated_at=datetime.now(UTC),
                updated_by_user_account_id=updated_by_user_account_id,
            ),
        )
