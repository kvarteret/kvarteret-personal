from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from time import perf_counter
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, or_, select

from app.auth.roles import UserRole
from app.cache import TTLCache
from app.config import get_settings
from app.db.repository import SqlAlchemyRepository
from app.db.tables import group_admin_memberships, user_accounts
from app.observability import log_operation_timing
from app.services.common import coerce_datetime

logger = logging.getLogger("app.performance")


@dataclass(slots=True)
class UserListItem:
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
class UserDetail:
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


class UsersServiceProtocol(Protocol):
    async def list_users(self, query: str | None = None, limit: int = 100) -> list[UserListItem]: ...
    async def get_user_detail(self, user_account_id: int) -> UserDetail | None: ...


class UsersService(SqlAlchemyRepository):
    def __init__(self) -> None:
        super().__init__()
        cache_ttl_seconds = get_settings().users_cache_ttl_seconds
        self._list_cache: TTLCache[tuple[str | None, int], list[UserListItem]] = TTLCache(
            ttl_seconds=cache_ttl_seconds,
            max_entries=128,
        )
        self._detail_cache: TTLCache[int, UserDetail] = TTLCache(
            ttl_seconds=cache_ttl_seconds,
            max_entries=256,
        )

    async def list_users(self, query: str | None = None, limit: int = 100) -> list[UserListItem]:
        started_at = perf_counter()
        safe_limit = max(1, min(limit, 200))
        normalized_query = _normalize_query(query)
        cache_key = (normalized_query, safe_limit)
        cached = self._list_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            users = await self._list_users_via_database(query=normalized_query, limit=safe_limit)
            self._list_cache.set(cache_key, users)
            return users
        finally:
            log_operation_timing(logger, operation="users.list", started_at=started_at, details={"limit": safe_limit})

    async def get_user_detail(self, user_account_id: int) -> UserDetail | None:
        cached = self._detail_cache.get(user_account_id)
        if cached is not None:
            return cached
        user = await self._get_user_detail_via_database(user_account_id)
        if user is not None:
            self._detail_cache.set(user_account_id, user)
        else:
            self._detail_cache.pop(user_account_id)
        return user

    async def _list_users_via_database(self, query: str | None = None, limit: int = 100) -> list[UserListItem]:
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
                func.count(group_admin_memberships.c.gruppe_id).label("group_admin_group_count"),
            )
            .select_from(
                user_accounts.outerjoin(
                    group_admin_memberships,
                    group_admin_memberships.c.auth_user_id == user_accounts.c.auth_user_id,
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
            UserListItem(
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

    async def _get_user_detail_via_database(self, user_account_id: int) -> UserDetail | None:
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
        return UserDetail(
            user_account_id=row["id"],
            auth_user_id=row["auth_user_id"],
            legacy_user_id=row.get("legacy_user_id"),
            username=row["username"],
            email=row["email"],
            display_name=row.get("display_name"),
            role=UserRole(row["role"]),
            last_login=coerce_datetime(row.get("last_login")),
            created_at=coerce_datetime(row["created_at"]),
            migrated_at=coerce_datetime(row.get("migrated_at")),
            group_admin_group_ids=memberships.get(row["auth_user_id"], []),
        )

    async def _load_group_admin_ids(self, auth_user_ids: list[UUID]) -> dict[UUID, list[int]]:
        if not auth_user_ids:
            return {}
        stmt = (
            select(group_admin_memberships.c.auth_user_id, group_admin_memberships.c.gruppe_id)
            .where(group_admin_memberships.c.auth_user_id.in_(auth_user_ids))
            .order_by(group_admin_memberships.c.auth_user_id.asc(), group_admin_memberships.c.gruppe_id.asc())
        )
        memberships: dict[UUID, list[int]] = {auth_user_id: [] for auth_user_id in auth_user_ids}
        for row in await self.fetch_all_mappings(stmt):
            memberships.setdefault(row["auth_user_id"], []).append(row["gruppe_id"])
        return memberships


def _normalize_query(query: str | None) -> str | None:
    if query is None:
        return None
    normalized = query.strip()
    return normalized or None
