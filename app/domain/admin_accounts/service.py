from __future__ import annotations

import logging
from time import perf_counter
from typing import Protocol
from uuid import UUID


from app.auth.roles import UserRole
from app.cache import TTLCache
from app.observability import log_operation_timing

from app.domain.admin_accounts.models import AdminAccountDetail, AdminAccountListItem
from app.domain.admin_accounts.repository import AdminAccountsRepository

# Re-export for backward compatibility
__all__ = [
    "AdminAccountDetail",
    "AdminAccountListItem",
    "AdminAccountsService",
    "AdminAccountsServiceProtocol",
]

logger = logging.getLogger("app.performance")


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


class AdminAccountsService:
    def __init__(
        self,
        repository: AdminAccountsRepository,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self.repository = repository
        self._list_cache: TTLCache[
            tuple[str | None, int], list[AdminAccountListItem]
        ] = TTLCache(ttl_seconds=cache_ttl_seconds, max_entries=128)
        self._detail_cache: TTLCache[int, AdminAccountDetail] = TTLCache(
            ttl_seconds=cache_ttl_seconds, max_entries=256
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
            admin_accounts = await self.repository.list_admin_accounts(
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
        user = await self.repository.get_admin_account_detail(user_account_id)
        if user is not None:
            self._detail_cache.set(user_account_id, user)
        else:
            self._detail_cache.pop(user_account_id)
        return user

    async def get_admin_account_detail_for_auth_user(
        self, auth_user_id: UUID
    ) -> AdminAccountDetail | None:
        user_account_id = (
            await self.repository.find_user_account_id_by_auth_user_id(auth_user_id)
        )
        if user_account_id is None:
            return None
        return await self.get_admin_account_detail(user_account_id)

    async def update_admin_account(
        self,
        *,
        user_account_id: int,
        username: str,
        email: str,
        display_name: str | None,
        role: UserRole,
    ) -> AdminAccountDetail | None:
        await self.repository.update_admin_account(
            user_account_id=user_account_id,
            username=username.strip(),
            email=email.strip(),
            display_name=_normalize_optional_text(display_name),
            role=role,
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
        if await self.repository.check_username_or_email_exists(
            username=normalized_username, email=normalized_email
        ):
            raise ValueError(
                "Det finnes allerede en admin-konto med dette brukernavnet eller denne e-posten."
            )
        user_account_id = await self.repository.create_admin_account(
            auth_user_id=auth_user_id,
            username=normalized_username,
            email=normalized_email,
            display_name=normalized_display_name,
            role=role,
        )
        self._detail_cache.pop(user_account_id)
        self._list_cache.clear()
        admin_account = await self.get_admin_account_detail(user_account_id)
        if admin_account is None:
            raise ValueError("Klarte ikke å opprette admin-kontoen.")
        return admin_account

    async def delete_admin_account(
        self, *, user_account_id: int, auth_user_id: UUID
    ) -> None:
        await self.repository.delete_admin_account(
            user_account_id=user_account_id, auth_user_id=auth_user_id
        )
        self._detail_cache.pop(user_account_id)
        self._list_cache.clear()


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
