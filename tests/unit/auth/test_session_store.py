from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.auth.models import AuthenticatedUser, WebSession
from app.auth.roles import UserRole
from app.auth.session_store import SessionStore
from app.config import Settings


class FakeRepository:
    def __init__(self) -> None:
        self.load_calls = 0
        self.deleted_sessions: list[str] = []

    async def create_session(self, **kwargs) -> WebSession:
        return WebSession(
            session_id=kwargs["session_id"],
            auth_user_id=kwargs["auth_user_id"],
            user_account_id=kwargs["user_account_id"],
            expires_at=kwargs["expires_at"],
        )

    async def load_authenticated_user_for_session(self, session_id: str):
        self.load_calls += 1
        return (
            WebSession(
                session_id=session_id,
                auth_user_id=uuid4(),
                user_account_id=10,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            ),
            AuthenticatedUser(
                auth_user_id=uuid4(),
                user_account_id=10,
                username="admin",
                email="admin.user@example.test",
                display_name="System User",
                role=UserRole.ADMIN,
            ),
        )

    async def delete_session(self, session_id: str) -> None:
        self.deleted_sessions.append(session_id)


@pytest.mark.asyncio
async def test_session_store_caches_loaded_sessions() -> None:
    repository = FakeRepository()
    store = SessionStore(repository, Settings(session_cache_ttl_seconds=60))

    first = await store.load_authenticated_user("session-1")
    second = await store.load_authenticated_user("session-1")

    assert first is not None
    assert second is not None
    assert repository.load_calls == 1


@pytest.mark.asyncio
async def test_session_store_delete_session_invalidates_cache() -> None:
    repository = FakeRepository()
    store = SessionStore(repository, Settings(session_cache_ttl_seconds=60))

    await store.load_authenticated_user("session-1")
    await store.delete_session("session-1")
    await store.load_authenticated_user("session-1")

    assert repository.deleted_sessions == ["session-1"]
    assert repository.load_calls == 2
