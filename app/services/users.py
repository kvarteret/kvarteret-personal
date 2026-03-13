from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Protocol
from uuid import UUID

from app.auth.roles import UserRole
from app.postgrest import PostgrestClient, get_postgrest_client


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


class UsersService:
    def __init__(self, postgrest_client: PostgrestClient | None = None) -> None:
        self.postgrest_client = postgrest_client

    async def list_users(self, query: str | None = None, limit: int = 100) -> list[UserListItem]:
        if self.postgrest_client is None:
            raise RuntimeError("PostgREST-backed user reads are not configured yet.")
        safe_limit = max(1, min(limit, 200))
        filters: dict[str, str] = {}
        if query and query.strip():
            pattern = _postgrest_ilike_pattern(query.strip())
            filters["or"] = (
                f"(username.ilike.{pattern},email.ilike.{pattern},"
                f"display_name.ilike.{pattern})"
            )
        rows = await self.postgrest_client.select_rows(
            "user_accounts",
            select="id,auth_user_id,legacy_user_id,username,email,display_name,role,last_login,group_admin_memberships(gruppe_id)",
            filters=filters,
            order="role.asc,username.asc",
            limit=safe_limit,
        )
        return [
            UserListItem(
                user_account_id=row["id"],
                auth_user_id=UUID(row["auth_user_id"]),
                legacy_user_id=row.get("legacy_user_id"),
                username=row["username"],
                email=row["email"],
                display_name=row.get("display_name"),
                role=UserRole(row["role"]),
                last_login=_coerce_datetime(row.get("last_login")),
                group_admin_group_ids=_extract_group_ids(row.get("group_admin_memberships")),
                group_admin_group_count=len(_extract_group_ids(row.get("group_admin_memberships"))),
            )
            for row in rows
        ]

    async def get_user_detail(self, user_account_id: int) -> UserDetail | None:
        if self.postgrest_client is None:
            raise RuntimeError("PostgREST-backed user reads are not configured yet.")
        rows = await self.postgrest_client.select_rows(
            "user_accounts",
            select="id,auth_user_id,legacy_user_id,username,email,display_name,role,last_login,created_at,migrated_at,group_admin_memberships(gruppe_id)",
            filters={"id": f"eq.{user_account_id}"},
            limit=1,
        )
        if not rows:
            return None
        row = rows[0]
        return UserDetail(
            user_account_id=row["id"],
            auth_user_id=UUID(row["auth_user_id"]),
            legacy_user_id=row.get("legacy_user_id"),
            username=row["username"],
            email=row["email"],
            display_name=row.get("display_name"),
            role=UserRole(row["role"]),
            last_login=_coerce_datetime(row.get("last_login")),
            created_at=_coerce_datetime(row["created_at"]),
            migrated_at=_coerce_datetime(row.get("migrated_at")),
            group_admin_group_ids=_extract_group_ids(row.get("group_admin_memberships")),
        )


def _extract_group_ids(memberships) -> list[int]:
    if not memberships:
        return []
    return [m["gruppe_id"] for m in memberships if m.get("gruppe_id") is not None]


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _postgrest_ilike_pattern(value: str) -> str:
    escaped = value.replace(",", "\\,").replace("(", "\\(").replace(")", "\\)")
    return f"*{escaped}*"


@lru_cache(maxsize=1)
def get_users_service() -> UsersService:
    try:
        postgrest_client = get_postgrest_client()
    except Exception:
        postgrest_client = None
    return UsersService(postgrest_client=postgrest_client)
