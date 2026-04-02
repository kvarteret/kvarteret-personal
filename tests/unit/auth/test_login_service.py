from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.auth.legacy_passwords import build_aspnet_identity_v3_hash
from app.auth.login_service import LoginError, LoginService
from app.auth.models import LegacyUser, UserAccount, WebSession
from app.auth.roles import UserRole


class FakeRepository:
    def __init__(self) -> None:
        self.user_account: UserAccount | None = None
        self.legacy_user: LegacyUser | None = None
        self.legacy_roles: list[str] = []
        self.group_ids: list[int] = []
        self.recorded_events: list[tuple[str, int]] = []
        self.replaced_memberships: list[tuple[UUID, list[int]]] = []
        self.user_account_identifiers: list[str] = []
        self.legacy_identifiers: list[str] = []

    async def get_user_account_by_identifier(self, identifier: str) -> UserAccount | None:
        self.user_account_identifiers.append(identifier)
        if self.user_account and identifier.lower() in {self.user_account.username.lower(), self.user_account.email.lower()}:
            return self.user_account
        return None

    async def get_legacy_user_by_identifier(self, identifier: str) -> LegacyUser | None:
        self.legacy_identifiers.append(identifier)
        if self.legacy_user and identifier.lower() in {self.legacy_user.username.lower(), (self.legacy_user.email or "").lower()}:
            return self.legacy_user
        return None

    async def get_legacy_roles(self, legacy_user_id: int) -> list[str]:
        return self.legacy_roles

    async def get_legacy_group_ids(self, legacy_user_id: int) -> list[int]:
        return self.group_ids

    async def upsert_user_account(self, *, auth_user_id: UUID, legacy_user: LegacyUser, role: UserRole) -> UserAccount:
        self.user_account = UserAccount(
            id=7,
            auth_user_id=auth_user_id,
            legacy_user_id=legacy_user.id,
            username=legacy_user.username,
            email=legacy_user.email or f"legacy-{legacy_user.id}@invalid.local",
            display_name=legacy_user.display_name,
            role=role,
            last_login=datetime.now(UTC),
        )
        return self.user_account

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
            legacy_user_id=None,
            username=username,
            email=email,
            display_name=display_name,
            role=role,
            last_login=datetime.now(UTC),
        )

    async def replace_group_admin_memberships(self, auth_user_id: UUID, group_ids: list[int]) -> None:
        self.replaced_memberships.append((auth_user_id, group_ids))

    async def record_migration_event(self, *, legacy_user_id: int, auth_user_id: UUID | None, email: str | None, outcome: str, details: str | None = None) -> None:
        self.recorded_events.append((outcome, legacy_user_id))

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
        return WebSession(session_id=session_id, auth_user_id=auth_user_id, user_account_id=user_account_id, expires_at=expires_at)

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

    async def create_user_from_legacy(self, legacy_user: LegacyUser, password: str) -> UUID:
        return self.created_user_id

    async def create_user(self, *, email: str, password: str, metadata: dict | None = None) -> UUID:
        return self.created_user_id

    async def invite_user(self, *, email: str, metadata: dict | None = None, redirect_to: str | None = None) -> UUID:
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
async def test_login_with_existing_migrated_account_uses_supabase_password_login() -> None:
    repository = FakeRepository()
    repository.user_account = UserAccount(
        id=9,
        auth_user_id=uuid4(),
        legacy_user_id=1,
        username="admin",
        email="migrated.user@example.test",
        display_name="Migrated User",
        role=UserRole.ADMIN,
        last_login=None,
    )
    supabase_auth = FakeSupabaseAuth()
    supabase_auth.sign_in_result = repository.user_account.auth_user_id
    service = LoginService(repository, supabase_auth, FakeSessionStore())

    result = await service.login_with_bridge(
        identifier="admin",
        password="correct",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert result.migrated_from_legacy is False
    assert result.user.username == "admin"
    assert result.session.user_account_id == 9
    assert repository.user_account_identifiers == ["admin"]


@pytest.mark.asyncio
async def test_login_with_legacy_account_bridges_to_supabase_auth() -> None:
    repository = FakeRepository()
    repository.legacy_user = LegacyUser(
        id=1,
        username="admin",
        email="migrated.user@example.test",
        display_name="Migrated User",
        password_hash=build_aspnet_identity_v3_hash(
            "Password123",
            salt=bytes.fromhex("00112233445566778899aabbccddeeff"),
        ),
    )
    repository.legacy_roles = ["Admin"]
    repository.group_ids = [10, 20]
    supabase_auth = FakeSupabaseAuth()
    service = LoginService(repository, supabase_auth, FakeSessionStore())

    result = await service.login_with_bridge(
        identifier="admin",
        password="Password123",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert result.migrated_from_legacy is True
    assert result.user.role == UserRole.ADMIN
    assert repository.recorded_events == [("migrated", 1)]
    assert repository.replaced_memberships == [(supabase_auth.created_user_id, [10, 20])]


@pytest.mark.asyncio
async def test_login_normalizes_identifier_before_repository_lookups() -> None:
    repository = FakeRepository()
    repository.legacy_user = LegacyUser(
        id=1,
        username="admin",
        email="migrated.user@example.test",
        display_name="Migrated User",
        password_hash=build_aspnet_identity_v3_hash(
            "Password123",
            salt=bytes.fromhex("00112233445566778899aabbccddeeff"),
        ),
    )
    repository.legacy_roles = ["Admin"]
    service = LoginService(repository, FakeSupabaseAuth(), FakeSessionStore())

    await service.login_with_bridge(
        identifier="  Admin ",
        password="Password123",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert repository.user_account_identifiers == ["admin"]
    assert repository.legacy_identifiers == ["admin"]


@pytest.mark.asyncio
async def test_login_with_invalid_credentials_raises() -> None:
    repository = FakeRepository()
    repository.legacy_user = LegacyUser(
        id=1,
        username="admin",
        email="migrated.user@example.test",
        display_name="Migrated User",
        password_hash=build_aspnet_identity_v3_hash(
            "Password123",
            salt=bytes.fromhex("00112233445566778899aabbccddeeff"),
        ),
    )
    service = LoginService(repository, FakeSupabaseAuth(), FakeSessionStore())

    with pytest.raises(LoginError):
        await service.login_with_bridge(
            identifier="admin",
            password="wrong",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
