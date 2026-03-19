from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Protocol
from uuid import UUID

from app.cache import TTLCache
from app.auth.models import AuthenticatedUser, WebSession
from app.config import Settings


class SessionRepositoryProtocol(Protocol):
    async def create_session(
        self,
        *,
        session_id: str,
        auth_user_id: UUID,
        user_account_id: int | None,
        impersonator_auth_user_id: UUID | None = None,
        impersonator_user_account_id: int | None = None,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> WebSession: ...
    async def load_authenticated_user_for_session(self, session_id: str) -> tuple[WebSession, AuthenticatedUser] | None: ...
    async def delete_session(self, session_id: str) -> None: ...


class SessionStoreProtocol(Protocol):
    async def create_session(
        self,
        *,
        auth_user_id: UUID,
        user_account_id: int | None,
        impersonator_auth_user_id: UUID | None = None,
        impersonator_user_account_id: int | None = None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> WebSession: ...
    async def load_authenticated_user(self, session_id: str) -> tuple[WebSession, AuthenticatedUser] | None: ...
    async def delete_session(self, session_id: str) -> None: ...
    def invalidate_session_cache(self, session_id: str) -> None: ...


class SessionStore:
    def __init__(self, repository: SessionRepositoryProtocol, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings
        self._cache: TTLCache[str, CachedSession] = TTLCache(
            ttl_seconds=settings.session_cache_ttl_seconds,
            max_entries=2048,
        )

    async def create_session(
        self,
        *,
        auth_user_id,
        user_account_id: int | None,
        impersonator_auth_user_id=None,
        impersonator_user_account_id: int | None = None,
        ip_address: str | None,
        user_agent: str | None,
        ) -> WebSession:
        session_id = token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=self.settings.session_ttl_hours)
        session = await self.repository.create_session(
            session_id=session_id,
            auth_user_id=auth_user_id,
            user_account_id=user_account_id,
            impersonator_auth_user_id=impersonator_auth_user_id,
            impersonator_user_account_id=impersonator_user_account_id,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._cache.pop(session_id)
        return session

    async def load_authenticated_user(self, session_id: str) -> tuple[WebSession, AuthenticatedUser] | None:
        cached = self._cache.get(session_id)
        now = datetime.now(UTC)
        if cached:
            if cached.web_session.expires_at <= now:
                self._cache.pop(session_id)
            else:
                return cached.web_session, cached.user

        auth_context = await self.repository.load_authenticated_user_for_session(session_id)
        if auth_context is None:
            self._cache.pop(session_id)
            return None

        web_session, user = auth_context
        self._cache.set(
            session_id,
            CachedSession(
                web_session=web_session,
                user=user,
            ),
        )
        return auth_context

    async def delete_session(self, session_id: str) -> None:
        self._cache.pop(session_id)
        await self.repository.delete_session(session_id)

    def invalidate_session_cache(self, session_id: str) -> None:
        self._cache.pop(session_id)


@dataclass(slots=True)
class CachedSession:
    web_session: WebSession
    user: AuthenticatedUser
