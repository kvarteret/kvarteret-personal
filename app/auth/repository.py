from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.auth.models import AuthenticatedUser, LegacyUser, UserAccount, WebSession
from app.auth.roles import UserRole
from app.db.repository import SqlAlchemyRepository
from app.db.tables import (
    aspnetroles,
    aspnetuserroles,
    aspnetusers,
    auth_migration_events,
    group_admin_memberships,
    grupper_admin_kobling,
    user_accounts,
    web_sessions,
)


class AuthRepositoryProtocol(Protocol):
    async def get_user_account_by_identifier(self, identifier: str) -> UserAccount | None: ...
    async def get_legacy_user_by_identifier(self, identifier: str) -> LegacyUser | None: ...
    async def get_legacy_roles(self, legacy_user_id: int) -> list[str]: ...
    async def get_legacy_group_ids(self, legacy_user_id: int) -> list[int]: ...
    async def create_direct_user_account(
        self,
        *,
        auth_user_id: UUID,
        username: str,
        email: str,
        display_name: str | None,
        role: UserRole,
    ) -> UserAccount: ...
    async def upsert_user_account(
        self,
        *,
        auth_user_id: UUID,
        legacy_user: LegacyUser,
        role: UserRole,
    ) -> UserAccount: ...
    async def replace_group_admin_memberships(self, auth_user_id: UUID, group_ids: list[int]) -> None: ...
    async def record_migration_event(
        self,
        *,
        legacy_user_id: int,
        auth_user_id: UUID | None,
        email: str | None,
        outcome: str,
        details: str | None = None,
    ) -> None: ...
    async def create_session(
        self,
        *,
        session_id: str,
        auth_user_id: UUID,
        user_account_id: int | None,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> WebSession: ...
    async def load_authenticated_user_for_session(self, session_id: str) -> tuple[WebSession, AuthenticatedUser] | None: ...
    async def delete_session(self, session_id: str) -> None: ...


USER_ACCOUNT_COLUMNS = (
    user_accounts.c.id,
    user_accounts.c.auth_user_id,
    user_accounts.c.legacy_user_id,
    user_accounts.c.username,
    user_accounts.c.email,
    user_accounts.c.display_name,
    user_accounts.c.role,
    user_accounts.c.last_login,
)

LEGACY_USER_COLUMNS = (
    aspnetusers.c.id,
    aspnetusers.c.username,
    aspnetusers.c.email,
    aspnetusers.c.name,
    aspnetusers.c.passwordhash,
)


class DatabaseAuthRepository(SqlAlchemyRepository):
    async def get_user_account_by_identifier(self, identifier: str) -> UserAccount | None:
        lowered = identifier.lower()
        stmt = (
            select(*USER_ACCOUNT_COLUMNS)
            .where(
                or_(
                    func.lower(user_accounts.c.username) == lowered,
                    func.lower(user_accounts.c.email) == lowered,
                )
            )
            .limit(1)
        )
        row = await self.fetch_first_mapping(stmt)
        return _map_user_account(row) if row else None

    async def get_legacy_user_by_identifier(self, identifier: str) -> LegacyUser | None:
        lowered = identifier.lower()
        stmt = (
            select(*LEGACY_USER_COLUMNS)
            .where(
                or_(
                    func.lower(aspnetusers.c.username) == lowered,
                    func.lower(aspnetusers.c.email) == lowered,
                )
            )
            .limit(1)
        )
        row = await self.fetch_first_mapping(stmt)
        if not row or not row["passwordhash"]:
            return None
        return LegacyUser(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            display_name=row["name"],
            password_hash=row["passwordhash"],
        )

    async def get_legacy_roles(self, legacy_user_id: int) -> list[str]:
        stmt = (
            select(aspnetroles.c.name)
            .select_from(aspnetuserroles.join(aspnetroles, aspnetroles.c.id == aspnetuserroles.c.roleid))
            .where(aspnetuserroles.c.userid == legacy_user_id)
            .order_by(aspnetroles.c.name)
        )
        return await self.fetch_scalars_all(stmt)

    async def get_legacy_group_ids(self, legacy_user_id: int) -> list[int]:
        stmt = (
            select(grupper_admin_kobling.c.id_gruppe)
            .where(grupper_admin_kobling.c.id_user == legacy_user_id)
            .order_by(grupper_admin_kobling.c.id_gruppe)
        )
        return await self.fetch_scalars_all(stmt)

    async def create_direct_user_account(
        self,
        *,
        auth_user_id: UUID,
        username: str,
        email: str,
        display_name: str | None,
        role: UserRole,
    ) -> UserAccount:
        stmt = (
            insert(user_accounts)
            .values(
                auth_user_id=auth_user_id,
                username=username,
                email=email,
                display_name=display_name,
                role=role.value,
                migrated_at=func.current_timestamp(),
            )
            .returning(*USER_ACCOUNT_COLUMNS)
        )
        row = await self.execute_one_mapping(stmt)
        return _map_user_account(row)

    async def upsert_user_account(
        self,
        *,
        auth_user_id: UUID,
        legacy_user: LegacyUser,
        role: UserRole,
    ) -> UserAccount:
        now = datetime.now(UTC)
        insert_stmt = pg_insert(user_accounts).values(
            auth_user_id=auth_user_id,
            legacy_user_id=legacy_user.id,
            username=legacy_user.username,
            email=legacy_user.email or f"legacy-{legacy_user.id}@invalid.local",
            display_name=legacy_user.display_name,
            role=role.value,
            last_login=now,
            migrated_at=now,
        )
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[user_accounts.c.legacy_user_id],
            set_={
                "auth_user_id": insert_stmt.excluded.auth_user_id,
                "username": insert_stmt.excluded.username,
                "email": insert_stmt.excluded.email,
                "display_name": insert_stmt.excluded.display_name,
                "role": insert_stmt.excluded.role,
                "last_login": insert_stmt.excluded.last_login,
                "migrated_at": insert_stmt.excluded.migrated_at,
                "updated_at": func.current_timestamp(),
            },
        ).returning(*USER_ACCOUNT_COLUMNS)
        row = await self.execute_one_mapping(stmt)
        return _map_user_account(row)

    async def replace_group_admin_memberships(self, auth_user_id: UUID, group_ids: list[int]) -> None:
        async def replace(session):
            await session.execute(delete(group_admin_memberships).where(group_admin_memberships.c.auth_user_id == auth_user_id))
            if group_ids:
                await session.execute(
                    insert(group_admin_memberships),
                    [{"auth_user_id": auth_user_id, "gruppe_id": group_id} for group_id in group_ids],
                )

        await self.execute_in_transaction(replace)

    async def record_migration_event(
        self,
        *,
        legacy_user_id: int,
        auth_user_id: UUID | None,
        email: str | None,
        outcome: str,
        details: str | None = None,
    ) -> None:
        stmt = insert(auth_migration_events).values(
            legacy_user_id=legacy_user_id,
            auth_user_id=auth_user_id,
            email=email,
            outcome=outcome,
            details=details,
        )
        await self.execute(stmt)

    async def create_session(
        self,
        *,
        session_id: str,
        auth_user_id: UUID,
        user_account_id: int | None,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> WebSession:
        stmt = insert(web_sessions).values(
            session_id=session_id,
            auth_user_id=auth_user_id,
            user_account_id=user_account_id,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.execute(stmt)
        return WebSession(
            session_id=session_id,
            auth_user_id=auth_user_id,
            user_account_id=user_account_id,
            expires_at=expires_at,
        )

    async def load_authenticated_user_for_session(self, session_id: str) -> tuple[WebSession, AuthenticatedUser] | None:
        stmt = (
            select(
                web_sessions.c.session_id,
                web_sessions.c.auth_user_id,
                web_sessions.c.user_account_id,
                web_sessions.c.expires_at,
                user_accounts.c.username,
                user_accounts.c.email,
                user_accounts.c.display_name,
                user_accounts.c.role,
            )
            .select_from(web_sessions.outerjoin(user_accounts, user_accounts.c.id == web_sessions.c.user_account_id))
            .where(web_sessions.c.session_id == session_id, web_sessions.c.expires_at > func.current_timestamp())
            .limit(1)
        )
        row = await self.fetch_first_mapping(stmt)
        if not row or row["user_account_id"] is None:
            return None
        web_session = WebSession(
            session_id=row["session_id"],
            auth_user_id=row["auth_user_id"],
            user_account_id=row["user_account_id"],
            expires_at=row["expires_at"],
        )
        user = AuthenticatedUser(
            auth_user_id=row["auth_user_id"],
            user_account_id=row["user_account_id"],
            username=row["username"],
            email=row["email"],
            display_name=row["display_name"],
            role=UserRole(row["role"]),
        )
        return web_session, user

    async def delete_session(self, session_id: str) -> None:
        await self.execute(delete(web_sessions).where(web_sessions.c.session_id == session_id))


def _map_user_account(row) -> UserAccount:
    return UserAccount(
        id=row["id"],
        auth_user_id=row["auth_user_id"],
        legacy_user_id=row["legacy_user_id"],
        username=row["username"],
        email=row["email"],
        display_name=row["display_name"],
        role=UserRole(row["role"]),
        last_login=row["last_login"],
    )
