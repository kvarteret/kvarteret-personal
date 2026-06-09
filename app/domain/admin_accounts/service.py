from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from time import perf_counter
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, func, or_, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.roles import UserRole
from app.cache import TTLCache
from app.db.repository import SqlAlchemyRepository
from app.db.tables import (
    group_admin_memberships,
    integration_tokens,
    user_accounts,
    web_sessions,
)
from app.observability import log_operation_timing
from app.shared.coercion import coerce_datetime, require_datetime

logger = logging.getLogger("app.performance")


@dataclass(slots=True)
class AdminAccountListItem:
    user_account_id: int
    auth_user_id: UUID
    legacy_user_id: int | None
    username: str
    email: str
    display_name: str | None
    role: UserRole
    last_login: datetime | None
    group_admin_group_ids: list[int]
    group_admin_group_count: int


@dataclass(slots=True)
class AdminAccountDetail:
    user_account_id: int
    auth_user_id: UUID
    legacy_user_id: int | None
    username: str
    email: str
    display_name: str | None
    role: UserRole
    last_login: datetime | None
    created_at: datetime
    migrated_at: datetime | None
    group_admin_group_ids: list[int]


class AdminAccountsServiceProtocol(Protocol):
    async def list_admin_accounts(
        self, query: str | None = None, limit: int = 100
    ) -> list[AdminAccountListItem]: ...
    async def get_admin_account_detail(
        self, user_account_id: int
    ) -> AdminAccountDetail | None: ...
    async def get_admin_account_detail_for_auth_user(
        self, auth_user_id: UUID
    ) -> AdminAccountDetail | None: ...
    async def create_admin_account(
        self,
        *,
        auth_user_id: UUID,
        username: str,
        email: str,
        display_name: str | None,
        role: UserRole,
    ) -> AdminAccountDetail: ...
    async def update_admin_account(
        self,
        *,
        user_account_id: int,
        username: str,
        email: str,
        display_name: str | None,
        role: UserRole,
    ) -> AdminAccountDetail | None: ...
    async def delete_admin_account(
        self, *, user_account_id: int, auth_user_id: UUID
    ) -> None: ...


class AdminAccountsService(SqlAlchemyRepository):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        cache_ttl_seconds: int = 60,
    ) -> None:
        super().__init__(session_factory=session_factory)
        self._list_cache: TTLCache[
            tuple[str | None, int], list[AdminAccountListItem]
        ] = TTLCache(
            ttl_seconds=cache_ttl_seconds,
            max_entries=128,
        )
        self._detail_cache: TTLCache[int, AdminAccountDetail] = TTLCache(
            ttl_seconds=cache_ttl_seconds,
            max_entries=256,
        )

    async def list_admin_accounts(
        self, query: str | None = None, limit: int = 100
    ) -> list[AdminAccountListItem]:
        started_at = perf_counter()
        safe_limit = max(1, min(limit, 200))
        normalized_query = _normalize_query(query)
        cache_key = (normalized_query, safe_limit)
        cached = self._list_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            admin_accounts = await self._list_admin_accounts_via_database(
                query=normalized_query, limit=safe_limit
            )
            self._list_cache.set(cache_key, admin_accounts)
            return admin_accounts
        finally:
            log_operation_timing(
                logger,
                operation="admin_accounts.list",
                started_at=started_at,
                details={"limit": safe_limit},
            )

    async def get_admin_account_detail(
        self, user_account_id: int
    ) -> AdminAccountDetail | None:
        cached = self._detail_cache.get(user_account_id)
        if cached is not None:
            return cached
        user = await self._get_admin_account_detail_via_database(user_account_id)
        if user is not None:
            self._detail_cache.set(user_account_id, user)
        else:
            self._detail_cache.pop(user_account_id)
        return user

    async def get_admin_account_detail_for_auth_user(
        self, auth_user_id: UUID
    ) -> AdminAccountDetail | None:
        stmt = (
            select(user_accounts.c.id)
            .where(user_accounts.c.auth_user_id == auth_user_id)
            .limit(1)
        )
        user_account_id = await self.fetch_scalar(stmt)
        if user_account_id is None:
            return None
        return await self.get_admin_account_detail(int(user_account_id))

    async def update_admin_account(
        self,
        *,
        user_account_id: int,
        username: str,
        email: str,
        display_name: str | None,
        role: UserRole,
    ) -> AdminAccountDetail | None:
        await self.execute(
            update(user_accounts)
            .where(user_accounts.c.id == user_account_id)
            .values(
                username=username.strip(),
                email=email.strip(),
                display_name=_normalize_optional_text(display_name),
                role=role.value,
                updated_at=func.current_timestamp(),
            )
        )
        self._detail_cache.pop(user_account_id)
        self._list_cache.clear()
        return await self.get_admin_account_detail(user_account_id)

    async def create_admin_account(
        self,
        *,
        auth_user_id: UUID,
        username: str,
        email: str,
        display_name: str | None,
        role: UserRole,
    ) -> AdminAccountDetail:
        normalized_username = username.strip()
        normalized_email = email.strip()
        normalized_display_name = _normalize_optional_text(display_name)
        if not normalized_username:
            raise ValueError("Username is required.")
        if not normalized_email:
            raise ValueError("Email is required.")
        existing_stmt = (
            select(user_accounts.c.id)
            .where(
                or_(
                    user_accounts.c.username == normalized_username,
                    user_accounts.c.email == normalized_email,
                )
            )
            .limit(1)
        )
        if await self.fetch_scalar(existing_stmt) is not None:
            raise ValueError(
                "Det finnes allerede en admin-konto med dette brukernavnet eller denne e-posten."
            )
        row = await self.execute_one_mapping(
            insert(user_accounts)
            .values(
                auth_user_id=auth_user_id,
                username=normalized_username,
                email=normalized_email,
                display_name=normalized_display_name,
                role=role.value,
                created_at=func.current_timestamp(),
                updated_at=func.current_timestamp(),
            )
            .returning(user_accounts.c.id)
        )
        user_account_id = row["id"]
        self._detail_cache.pop(user_account_id)
        self._list_cache.clear()
        admin_account = await self.get_admin_account_detail(user_account_id)
        if admin_account is None:
            raise ValueError("Klarte ikke å opprette admin-kontoen.")
        return admin_account

    async def delete_admin_account(
        self, *, user_account_id: int, auth_user_id: UUID
    ) -> None:
        async def delete_account(session: AsyncSession) -> None:
            await session.execute(
                update(integration_tokens)
                .where(
                    integration_tokens.c.updated_by_user_account_id == user_account_id
                )
                .values(updated_by_user_account_id=None)
            )
            await session.execute(
                delete(web_sessions).where(
                    or_(
                        web_sessions.c.user_account_id == user_account_id,
                        web_sessions.c.impersonator_user_account_id == user_account_id,
                        web_sessions.c.auth_user_id == auth_user_id,
                        web_sessions.c.impersonator_auth_user_id == auth_user_id,
                    )
                )
            )
            await session.execute(
                delete(group_admin_memberships).where(
                    group_admin_memberships.c.auth_user_id == auth_user_id
                )
            )
            await session.execute(
                delete(user_accounts).where(user_accounts.c.id == user_account_id)
            )

        await self.execute_in_transaction(delete_account)
        self._detail_cache.pop(user_account_id)
        self._list_cache.clear()

    async def _list_admin_accounts_via_database(
        self, query: str | None = None, limit: int = 100
    ) -> list[AdminAccountListItem]:
        stmt = (
            select(
                user_accounts.c.id,
                user_accounts.c.auth_user_id,
                user_accounts.c.legacy_user_id,
                user_accounts.c.username,
                user_accounts.c.email,
                user_accounts.c.display_name,
                user_accounts.c.role,
                user_accounts.c.last_login,
                func.count(group_admin_memberships.c.gruppe_id).label(
                    "group_admin_group_count"
                ),
            )
            .select_from(
                user_accounts.outerjoin(
                    group_admin_memberships,
                    group_admin_memberships.c.auth_user_id
                    == user_accounts.c.auth_user_id,
                )
            )
            .group_by(
                user_accounts.c.id,
                user_accounts.c.auth_user_id,
                user_accounts.c.legacy_user_id,
                user_accounts.c.username,
                user_accounts.c.email,
                user_accounts.c.display_name,
                user_accounts.c.role,
                user_accounts.c.last_login,
            )
            .order_by(user_accounts.c.role.asc(), user_accounts.c.username.asc())
            .limit(limit)
        )
        if query and query.strip():
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    user_accounts.c.username.ilike(pattern),
                    user_accounts.c.email.ilike(pattern),
                    user_accounts.c.display_name.ilike(pattern),
                )
            )
        rows = await self.fetch_all_mappings(stmt)
        return [
            AdminAccountListItem(
                user_account_id=row["id"],
                auth_user_id=row["auth_user_id"],
                legacy_user_id=row.get("legacy_user_id"),
                username=row["username"],
                email=row["email"],
                display_name=row.get("display_name"),
                role=UserRole(row["role"]),
                last_login=coerce_datetime(row.get("last_login")),
                group_admin_group_ids=[],
                group_admin_group_count=row["group_admin_group_count"] or 0,
            )
            for row in rows
        ]

    async def _get_admin_account_detail_via_database(
        self, user_account_id: int
    ) -> AdminAccountDetail | None:
        stmt = (
            select(
                user_accounts.c.id,
                user_accounts.c.auth_user_id,
                user_accounts.c.legacy_user_id,
                user_accounts.c.username,
                user_accounts.c.email,
                user_accounts.c.display_name,
                user_accounts.c.role,
                user_accounts.c.last_login,
                user_accounts.c.created_at,
                user_accounts.c.migrated_at,
            )
            .where(user_accounts.c.id == user_account_id)
            .limit(1)
        )
        row = await self.fetch_first_mapping(stmt)
        if row is None:
            return None
        memberships = await self._load_group_admin_ids([row["auth_user_id"]])
        return AdminAccountDetail(
            user_account_id=row["id"],
            auth_user_id=row["auth_user_id"],
            legacy_user_id=row.get("legacy_user_id"),
            username=row["username"],
            email=row["email"],
            display_name=row.get("display_name"),
            role=UserRole(row["role"]),
            last_login=coerce_datetime(row.get("last_login")),
            created_at=require_datetime(row["created_at"]),
            migrated_at=coerce_datetime(row.get("migrated_at")),
            group_admin_group_ids=memberships.get(row["auth_user_id"], []),
        )

    async def _load_group_admin_ids(
        self, auth_user_ids: list[UUID]
    ) -> dict[UUID, list[int]]:
        if not auth_user_ids:
            return {}
        stmt = (
            select(
                group_admin_memberships.c.auth_user_id,
                group_admin_memberships.c.gruppe_id,
            )
            .where(group_admin_memberships.c.auth_user_id.in_(auth_user_ids))
            .order_by(
                group_admin_memberships.c.auth_user_id.asc(),
                group_admin_memberships.c.gruppe_id.asc(),
            )
        )
        memberships: dict[UUID, list[int]] = {
            auth_user_id: [] for auth_user_id in auth_user_ids
        }
        for row in await self.fetch_all_mappings(stmt):
            memberships.setdefault(row["auth_user_id"], []).append(row["gruppe_id"])
        return memberships


def _normalize_query(query: str | None) -> str | None:
    if query is None:
        return None
    normalized = query.strip()
    return normalized or None


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
