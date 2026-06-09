from __future__ import annotations

import logging
from datetime import datetime
from time import perf_counter
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, func, insert, or_, select
from app.auth.models import AuthenticatedUser, UserAccount, WebSession
from app.auth.roles import UserRole
from app.db.repository import SqlAlchemyRepository
from app.db.tables import user_accounts, web_sessions
from app.observability import log_operation_timing

logger = logging.getLogger("app.performance")


class AuthRepositoryProtocol(Protocol):
    async def get_user_account_by_identifier(
        self, identifier: str
    ) -> UserAccount | None: ...
    async def create_direct_user_account(
        self,
        *,
        auth_user_id: UUID,
        username: str,
        email: str,
        display_name: str | None,
        role: UserRole,
    ) -> UserAccount: ...
    async def create_session(
        self,
        *,
        session_id: str,
        auth_user_id: UUID,
        user_account_id: int | None,
        impersonator_auth_user_id: UUID | None,
        impersonator_user_account_id: int | None,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> WebSession: ...
    async def load_authenticated_user_for_session(
        self, session_id: str
    ) -> tuple[WebSession, AuthenticatedUser] | None: ...
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


class DatabaseAuthRepository(SqlAlchemyRepository):
    async def get_user_account_by_identifier(
        self, identifier: str
    ) -> UserAccount | None:
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

    async def create_session(
        self,
        *,
        session_id: str,
        auth_user_id: UUID,
        user_account_id: int | None,
        impersonator_auth_user_id: UUID | None,
        impersonator_user_account_id: int | None,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> WebSession:
        stmt = insert(web_sessions).values(
            session_id=session_id,
            auth_user_id=auth_user_id,
            user_account_id=user_account_id,
            impersonator_auth_user_id=impersonator_auth_user_id,
            impersonator_user_account_id=impersonator_user_account_id,
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
            impersonator_user=None,
        )

    async def load_authenticated_user_for_session(
        self, session_id: str
    ) -> tuple[WebSession, AuthenticatedUser] | None:
        started_at = perf_counter()
        row = await self.fetch_first_mapping(
            _build_session_load_stmt(session_id=session_id)
        )
        try:
            if not row or row["user_account_id"] is None:
                return None
            impersonator_user = None
            if (
                row["impersonator_user_account_id"] is not None
                and row["impersonator_role"] is not None
            ):
                impersonator_auth_user_id = row["impersonator_auth_user_id"]
                if impersonator_auth_user_id is None:
                    return None
                impersonator_user = AuthenticatedUser(
                    auth_user_id=impersonator_auth_user_id,
                    user_account_id=row["impersonator_user_account_id"],
                    username=row["impersonator_username"],
                    email=row["impersonator_email"],
                    display_name=row["impersonator_display_name"],
                    role=UserRole(row["impersonator_role"]),
                )
            web_session = WebSession(
                session_id=row["session_id"],
                auth_user_id=row["auth_user_id"],
                user_account_id=row["user_account_id"],
                expires_at=row["expires_at"],
                impersonator_user=impersonator_user,
            )
            user = AuthenticatedUser(
                auth_user_id=row["auth_user_id"],
                user_account_id=row["user_account_id"],
                username=row["username"],
                email=row["email"],
                display_name=row["display_name"],
                role=UserRole(row["role"]),
                is_impersonated=impersonator_user is not None,
            )
            return web_session, user
        finally:
            log_operation_timing(
                logger, operation="auth.session.load", started_at=started_at
            )

    async def delete_session(self, session_id: str) -> None:
        await self.execute(
            delete(web_sessions).where(web_sessions.c.session_id == session_id)
        )


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


def _build_session_load_stmt(*, session_id: str):
    impersonator_accounts = user_accounts.alias("impersonator_accounts")
    return (
        select(
            web_sessions.c.session_id,
            web_sessions.c.auth_user_id,
            web_sessions.c.user_account_id,
            web_sessions.c.impersonator_auth_user_id,
            web_sessions.c.impersonator_user_account_id,
            web_sessions.c.expires_at,
            user_accounts.c.username,
            user_accounts.c.email,
            user_accounts.c.display_name,
            user_accounts.c.role,
            impersonator_accounts.c.username.label("impersonator_username"),
            impersonator_accounts.c.email.label("impersonator_email"),
            impersonator_accounts.c.display_name.label("impersonator_display_name"),
            impersonator_accounts.c.role.label("impersonator_role"),
        )
        .select_from(
            web_sessions.outerjoin(
                user_accounts, user_accounts.c.id == web_sessions.c.user_account_id
            ).outerjoin(
                impersonator_accounts,
                impersonator_accounts.c.id
                == web_sessions.c.impersonator_user_account_id,
            )
        )
        .where(
            web_sessions.c.session_id == session_id,
            web_sessions.c.expires_at > func.current_timestamp(),
        )
        .limit(1)
    )
