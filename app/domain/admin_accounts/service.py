from __future__ import annotations

import logging
from time import perf_counter
from typing import Protocol
from uuid import UUID

from email_validator import EmailNotValidError, validate_email

from app.auth.roles import UserRole
from app.cache import TTLCache
from app.errors import NotConfiguredError
from app.observability import log_operation_timing

from app.domain.admin_accounts.models import AdminAccountDetail, AdminAccountListItem
from app.domain.admin_accounts.repository import AdminAccountsRepository
from app.infrastructure.email.admin_account_templates import (
    AdminAccountEmailTemplateRendererProtocol,
)
from app.infrastructure.email.protocols import EmailSenderProtocol

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
    async def get_admin_account_detail_for_email(
        self, email: str
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
    async def send_onboarding_email(
        self,
        *,
        recipient_email: str,
        setup_url: str,
        display_name: str | None,
        username: str,
        role_name: str,
    ) -> None: ...
    async def mark_onboarding_email_sent(self, user_account_id: int) -> None: ...
    async def mark_onboarding_complete(self, auth_user_id: UUID) -> None: ...


class AdminAccountsService:
    def __init__(
        self,
        repository: AdminAccountsRepository,
        cache_ttl_seconds: int = 60,
        email_sender: EmailSenderProtocol | None = None,
        onboarding_email_renderer: AdminAccountEmailTemplateRendererProtocol
        | None = None,
    ) -> None:
        self.repository = repository
        self.email_sender = email_sender
        self.onboarding_email_renderer = onboarding_email_renderer
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

    async def get_admin_account_detail_for_email(
        self, email: str
    ) -> AdminAccountDetail | None:
        user_account_id = await self.repository.find_user_account_id_by_email(email)
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
        normalized_email = _normalize_email(email)
        normalized_username = _normalize_username(username)
        existing = await self.get_admin_account_detail(user_account_id)
        if existing is None:
            return None
        if normalized_email != _normalize_email(existing.email):
            raise ValueError(
                "E-postadressen kan ikke endres etter at admin-kontoen er opprettet."
            )
        if await self.repository.check_username_or_email_exists(
            username=normalized_username,
            email=normalized_email,
            exclude_user_account_id=user_account_id,
        ):
            raise ValueError(
                "Det finnes allerede en admin-konto med dette brukernavnet eller denne e-posten."
            )
        await self.repository.update_admin_account(
            user_account_id=user_account_id,
            username=normalized_username,
            email=normalized_email,
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
        normalized_username = _normalize_username(username)
        normalized_email = _normalize_email(email)
        normalized_display_name = _normalize_optional_text(display_name)
        if not normalized_username:
            raise ValueError("Username is required.")
        if not normalized_email:
            raise ValueError("Email is required.")
        existing_email_account_id = (
            await self.repository.find_user_account_id_by_email(normalized_email)
        )
        if existing_email_account_id is not None:
            existing = await self.get_admin_account_detail(existing_email_account_id)
            if (
                existing is not None
                and existing.auth_user_id == auth_user_id
                and existing.username.strip().lower() == normalized_username.lower()
            ):
                return existing
            raise ValueError(
                "Det finnes allerede en admin-konto med dette brukernavnet eller denne e-posten."
            )
        existing_username_account_id = (
            await self.repository.find_user_account_id_by_username(normalized_username)
        )
        if existing_username_account_id is not None:
            existing = await self.get_admin_account_detail(existing_username_account_id)
            if existing is not None and existing.auth_user_id == auth_user_id:
                return existing
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
        if user_account_id is None:
            # A unique index is the authoritative race guard. Re-read after a
            # savepoint rollback and make a retry of the same request a no-op.
            existing_email_account_id = (
                await self.repository.find_user_account_id_by_email(normalized_email)
            )
            if existing_email_account_id is None:
                raise ValueError("Admin-kontoen kunne ikke opprettes.")
            existing = await self.get_admin_account_detail(existing_email_account_id)
            if (
                existing is None
                or existing.auth_user_id != auth_user_id
                or existing.username.strip().lower() != normalized_username.lower()
            ):
                raise ValueError(
                    "Det finnes allerede en admin-konto med dette brukernavnet eller denne e-posten."
                )
            return existing
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

    async def send_onboarding_email(
        self,
        *,
        recipient_email: str,
        setup_url: str,
        display_name: str | None,
        username: str,
        role_name: str,
    ) -> None:
        if self.email_sender is None or self.onboarding_email_renderer is None:
            raise NotConfiguredError("Admin onboarding email is not configured.")
        rendered = self.onboarding_email_renderer.render_onboarding_email(
            setup_url=setup_url,
            display_name=display_name,
            username=username,
            role_name=role_name,
        )
        await self.email_sender.send_email(
            recipient_email=recipient_email,
            subject=rendered.subject,
            html_body=rendered.html_body,
        )

    async def mark_onboarding_email_sent(self, user_account_id: int) -> None:
        await self.repository.mark_onboarding_email_sent(user_account_id)
        self._detail_cache.pop(user_account_id)

    async def mark_onboarding_complete(self, auth_user_id: UUID) -> None:
        await self.repository.mark_onboarding_complete(auth_user_id)
        user_account_id = await self.repository.find_user_account_id_by_auth_user_id(
            auth_user_id
        )
        if user_account_id is not None:
            self._detail_cache.pop(user_account_id)


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


def _normalize_username(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Username is required.")
    return normalized


def _normalize_email(value: str) -> str:
    try:
        normalized = validate_email(
            value.strip(), check_deliverability=False
        ).normalized
    except EmailNotValidError as exc:
        raise ValueError("Skriv inn en gyldig e-postadresse.") from exc
    return normalized.lower()
