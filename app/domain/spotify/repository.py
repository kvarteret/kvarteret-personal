from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, insert, select, update

from app.db.repository import SqlAlchemyRepository
from app.domain.spotify.tables import integration_tokens

@dataclass(slots=True)
class StoredIntegrationToken:
    provider: str
    refresh_token: str
    updated_at: datetime
    updated_by_user_account_id: int | None


class IntegrationTokensRepository(SqlAlchemyRepository):
    async def get_token(self, provider: str) -> StoredIntegrationToken | None:
        row = await self.fetch_first_mapping(
            select(
                integration_tokens.c.provider,
                integration_tokens.c.refresh_token,
                integration_tokens.c.updated_at,
                integration_tokens.c.updated_by_user_account_id,
            ).where(integration_tokens.c.provider == provider)
        )
        if row is None:
            return None
        return StoredIntegrationToken(
            provider=row["provider"],
            refresh_token=row["refresh_token"],
            updated_at=row["updated_at"],
            updated_by_user_account_id=row["updated_by_user_account_id"],
        )

    async def save_token(
        self,
        *,
        provider: str,
        refresh_token: str,
        updated_at: datetime,
        updated_by_user_account_id: int | None,
    ) -> None:
        async def callback(session):
            existing = await session.scalar(
                select(integration_tokens.c.provider).where(
                    integration_tokens.c.provider == provider
                )
            )
            if existing is None:
                await session.execute(
                    insert(integration_tokens).values(
                        provider=provider,
                        refresh_token=refresh_token,
                        updated_at=updated_at,
                        updated_by_user_account_id=updated_by_user_account_id,
                    )
                )
            else:
                await session.execute(
                    update(integration_tokens)
                    .where(integration_tokens.c.provider == provider)
                    .values(
                        refresh_token=refresh_token,
                        updated_at=updated_at,
                        updated_by_user_account_id=updated_by_user_account_id,
                    )
                )

        await callback(self.session)

    async def delete_token(self, provider: str) -> None:
        await self.execute(
            delete(integration_tokens).where(integration_tokens.c.provider == provider)
        )
