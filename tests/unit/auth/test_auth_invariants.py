"""Test that a GoTrue user without a user_accounts row cannot login.

This invariant was discovered during the security audit: admin login
requires a user_accounts row before consulting GoTrue.  If a volunteer
has GoTrue credentials but no user_accounts row, they cannot establish
an admin session.  The test pins this invariant so it survives
refactoring — including M9's auth consolidation.
"""

import pytest

from app.auth.login_service import LoginError, LoginService
from app.auth.models import UserAccount
from app.auth.roles import UserRole
from app.auth.supabase_auth import SupabaseAuthGatewayProtocol


class FakeSessionStore:
    async def create_session(self, user_account_id, *, auth_user_id=None, ip_address=None, user_agent=None):
        return None


class FakeAuthRepo:
    async def get_user_account_by_identifier(self, identifier: str) -> UserAccount | None:
        return None


class FakeGoTrue(SupabaseAuthGatewayProtocol):
    def __init__(self):
        self.sign_in_called = False

    async def sign_in_with_password(self, email: str, password: str):
        self.sign_in_called = True
        return "auth-user-uuid-123"

    async def create_user(self, **kwargs):
        pass

    async def invite_user(self, **kwargs):
        pass

    async def generate_link(self, **kwargs):
        pass

    async def update_user_password(self, *args, **kwargs):
        pass

    async def update_password_with_access_token(self, *args, **kwargs):
        pass

    async def delete_user(self, *args, **kwargs):
        pass

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_gotrue_user_without_account_cannot_login():
    """A GoTrue user with valid credentials but no user_accounts row
    must not be able to establish an admin session."""
    fake_repo = FakeAuthRepo()
    fake_gotrue = FakeGoTrue()
    fake_session_store = FakeSessionStore()

    service = LoginService(
        repository=fake_repo,
        supabase_auth=fake_gotrue,
        session_store=fake_session_store,
    )

    with pytest.raises(LoginError):
        await service.login(
            identifier="volunteer@example.com",
            password="password123",
            ip_address=None,
            user_agent=None,
        )

    # GoTrue sign-in was never called because user_accounts lookup failed first.
    assert not fake_gotrue.sign_in_called


@pytest.mark.asyncio
async def test_gotrue_user_with_account_can_login():
    """A GoTrue user WITH a user_accounts row SHOULD be able to login."""
    class RepoWithAccount:
        async def get_user_account_by_identifier(self, identifier: str):
            return UserAccount(
                id=1,
                auth_user_id="auth-user-uuid-123",
                username="admin",
                email="admin@example.com",
                display_name=None,
                role=UserRole.ADMIN,
                last_login=None,
            )

    fake_repo = RepoWithAccount()
    fake_gotrue = FakeGoTrue()
    fake_session_store = FakeSessionStore()

    service = LoginService(
        repository=fake_repo,
        supabase_auth=fake_gotrue,
        session_store=fake_session_store,
    )

    result = await service.login(
        identifier="admin@example.com",
        password="password123",
        ip_address=None,
        user_agent=None,
    )

    assert result is not None
    assert fake_gotrue.sign_in_called
