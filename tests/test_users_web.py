from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.cookies import sign_session_id
from app.auth.models import AuthenticatedUser, WebSession
from app.auth.roles import UserRole
from app.main import create_app
from app.services.users import UserDetail, UserListItem


class FakeUsersService:
    async def list_users(self, query: str | None = None, limit: int = 100) -> list[UserListItem]:
        return [
            UserListItem(
                user_account_id=7,
                auth_user_id=uuid4(),
                legacy_user_id=4,
                username="sample.admin",
                email="sample.admin@example.test",
                display_name="Sample Admin",
                role=UserRole.ADMIN,
                last_login=datetime(2026, 3, 13, tzinfo=UTC),
                group_admin_group_ids=[2, 4],
                group_admin_group_count=2,
            )
        ]

    async def get_user_detail(self, user_account_id: int) -> UserDetail | None:
        if user_account_id != 7:
            return None
        return UserDetail(
            user_account_id=7,
            auth_user_id=uuid4(),
            legacy_user_id=4,
            username="sample.admin",
            email="sample.admin@example.test",
            display_name="Sample Admin",
            role=UserRole.ADMIN,
            last_login=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
            created_at=datetime(2026, 3, 12, 11, 0, tzinfo=UTC),
            migrated_at=datetime(2026, 3, 13, 9, 30, tzinfo=UTC),
            group_admin_group_ids=[2, 4],
        )


class FakeSessionStore:
    def __init__(self, role: UserRole) -> None:
        self.role = role

    async def load_authenticated_user(self, session_id: str):
        return (
            WebSession(
                session_id=session_id,
                auth_user_id=uuid4(),
                user_account_id=5,
                expires_at=datetime.now(UTC) + timedelta(hours=12),
            ),
            AuthenticatedUser(
                auth_user_id=uuid4(),
                user_account_id=5,
                username="admin",
                email="admin.user@example.test",
                display_name="System User",
                role=self.role,
            ),
        )

    async def delete_session(self, session_id: str) -> None:
        return None


def _make_client(role: UserRole = UserRole.ADMIN) -> TestClient:
    app = create_app()
    app.state.users_service = FakeUsersService()
    app.state.session_store = FakeSessionStore(role)
    client = TestClient(app)
    client.cookies.set("kvarteret_session", sign_session_id("session-123"))
    return client


def test_users_pages_render_for_admins() -> None:
    client = _make_client()

    list_response = client.get("/users")
    detail_response = client.get("/users/7")

    assert list_response.status_code == 200
    assert "Sample Admin" in list_response.text
    assert "Search by username, email, or display name" in list_response.text
    assert detail_response.status_code == 200
    assert "Group-admin scope" in detail_response.text
    assert "Group 2" in detail_response.text


def test_users_pages_forbid_non_admins() -> None:
    client = _make_client(role=UserRole.VOLUNTEER)

    response = client.get("/users")

    assert response.status_code == 403
