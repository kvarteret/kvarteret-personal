from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.auth.login_service import LoginError, LoginService
from app.auth.models import UserAccount, WebSession
from app.auth.roles import UserRole


class FakeRepository:
    def __init__(self) -> None:
        self.user_account: UserAccount | None = None
        self.user_account_identifiers: list[str] = []
        self.completed_auth_user_ids: list[UUID] = []

    async def get_user_account_by_identifier(
        self, identifier: str
    ) -> UserAccount | None:
        self.user_account_identifiers.append(identifier)
        if self.user_account and identifier.lower() in {
            self.user_account.username.lower(),
            self.user_account.email.lower(),
        }:
            return self.user_account
        return None

    async def mark_onboarding_complete(self, auth_user_id: UUID) -> None:
        self.completed_auth_user_ids.append(auth_user_id)

    async def create_direct_user_account(
        self,
        *,
        auth_user_id: UUID,
        username: str,
        email: str,
        display_name: str | None,
        role: UserRole,
    ) -> UserAccount:
        return UserAccount(
            id=8,
            auth_user_id=auth_user_id,
            username=username,
            email=email,
            display_name=display_name,
            role=role,
            last_login=datetime.now(UTC),
        )

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
    ) -> WebSession:
        return WebSession(
            session_id=session_id,
            auth_user_id=auth_user_id,
            user_account_id=user_account_id,
            expires_at=expires_at,
        )

    async def load_authenticated_user_for_session(self, session_id: str):
        raise NotImplementedError

    async def delete_session(self, session_id: str) -> None:
        return None


class FakeSupabaseAuth:
    def __init__(self) -> None:
        self.sign_in_result: UUID | None = None
        self.created_user_id = uuid4()

    async def sign_in_with_password(self, email: str, password: str) -> UUID | None:
        return self.sign_in_result

    async def create_user(
        self, *, email: str, password: str, metadata: dict | None = None
    ) -> UUID:
        return self.created_user_id

    async def invite_user(
        self,
        *,
        email: str,
        metadata: dict | None = None,
        redirect_to: str | None = None,
    ) -> UUID:
        return self.created_user_id

    async def update_user_password(self, auth_user_id: UUID, password: str) -> None:
        return None

    async def delete_user(self, auth_user_id: UUID) -> None:
        return None

    def close(self) -> None:
        return None


class FakeSessionStore:
    async def create_session(
        self,
        *,
        auth_user_id: UUID,
        user_account_id: int | None,
        impersonator_auth_user_id: UUID | None = None,
        impersonator_user_account_id: int | None = None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> WebSession:
        return WebSession(
            session_id="session-123",
            auth_user_id=auth_user_id,
            user_account_id=user_account_id,
            expires_at=datetime.now(UTC) + timedelta(hours=12),
        )

    async def load_authenticated_user(self, session_id: str):
        return None

    async def delete_session(self, session_id: str) -> None:
        return None

    def invalidate_session_cache(self, session_id: str) -> None:
        return None


@pytest.mark.asyncio
async def test_login_with_existing_account_uses_supabase_password_login() -> None:
    repository = FakeRepository()
    repository.user_account = UserAccount(
        id=9,
        auth_user_id=uuid4(),
        username="admin",
        email="admin@example.test",
        display_name="Admin User",
        role=UserRole.ADMIN,
        last_login=None,
    )
    supabase_auth = FakeSupabaseAuth()
    supabase_auth.sign_in_result = repository.user_account.auth_user_id
    service = LoginService(repository, supabase_auth, FakeSessionStore())

    result = await service.login(
        identifier="admin",
        password="correct",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert result.user.username == "admin"
    assert result.session.user_account_id == 9
    assert repository.user_account_identifiers == ["admin"]
    assert repository.completed_auth_user_ids == [repository.user_account.auth_user_id]


@pytest.mark.asyncio
async def test_login_with_unknown_identifier_raises() -> None:
    repository = FakeRepository()
    service = LoginService(repository, FakeSupabaseAuth(), FakeSessionStore())

    with pytest.raises(LoginError):
        await service.login(
            identifier="nobody",
            password="anything",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )


@pytest.mark.asyncio
async def test_login_with_invalid_password_raises() -> None:
    repository = FakeRepository()
    repository.user_account = UserAccount(
        id=1,
        auth_user_id=uuid4(),
        username="admin",
        email="admin@example.test",
        display_name="Admin",
        role=UserRole.ADMIN,
        last_login=None,
    )
    supabase_auth = FakeSupabaseAuth()
    supabase_auth.sign_in_result = None
    service = LoginService(repository, supabase_auth, FakeSessionStore())

    with pytest.raises(LoginError):
        await service.login(
            identifier="admin",
            password="wrong",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )


@pytest.mark.asyncio
async def test_login_normalizes_identifier_before_repository_lookups() -> None:
    repository = FakeRepository()
    repository.user_account = UserAccount(
        id=2,
        auth_user_id=uuid4(),
        username="admin",
        email="admin@example.test",
        display_name="Admin",
        role=UserRole.ADMIN,
        last_login=None,
    )
    supabase_auth = FakeSupabaseAuth()
    supabase_auth.sign_in_result = repository.user_account.auth_user_id
    service = LoginService(repository, supabase_auth, FakeSessionStore())

    await service.login(
        identifier="  Admin ",
        password="correct",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert repository.user_account_identifiers == ["admin"]
