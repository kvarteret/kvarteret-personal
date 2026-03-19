from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.models import WebSession
from app.auth.roles import UserRole
from app.dependencies import get_admin_accounts_service, get_session_store, get_supabase_auth_gateway
from app.main import create_app
from app.services.admin_accounts import AdminAccountDetail, AdminAccountListItem
from tests.helpers import make_authenticated_user, override_authenticated_user


class FakeAdminAccountsService:
    def __init__(self) -> None:
        self.created_account = None

    async def list_admin_accounts(self, query: str | None = None, limit: int = 100) -> list[AdminAccountListItem]:
        return [
            AdminAccountListItem(
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

    async def get_admin_account_detail(self, user_account_id: int) -> AdminAccountDetail | None:
        if user_account_id not in {5, 7}:
            return None
        return AdminAccountDetail(
            user_account_id=user_account_id,
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

    async def update_admin_account(self, *, user_account_id: int, username: str, email: str, display_name: str | None, role: UserRole):
        return await self.get_admin_account_detail(user_account_id)

    async def create_admin_account(
        self,
        *,
        auth_user_id,
        username: str,
        email: str,
        display_name: str | None,
        role: UserRole,
    ) -> AdminAccountDetail:
        self.created_account = (auth_user_id, username, email, display_name, role)
        return AdminAccountDetail(
            user_account_id=11,
            auth_user_id=auth_user_id,
            legacy_user_id=None,
            username=username,
            email=email,
            display_name=display_name,
            role=role,
            last_login=None,
            created_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
            migrated_at=None,
            group_admin_group_ids=[],
        )

class FakeSupabaseAuthGateway:
    def __init__(self) -> None:
        self.created_user = None
        self.invited_user = None
        self.deleted_user = None
        self.updated_password = None

    async def sign_in_with_password(self, email: str, password: str):
        if password != "CorrectPassword123":
            return None
        return self.updated_password[0] if self.updated_password else self.created_user[0] if self.created_user else None

    async def create_user_from_legacy(self, legacy_user, password: str):
        raise NotImplementedError

    async def create_user(self, *, email: str, password: str, metadata: dict | None = None):
        auth_user_id = uuid4()
        self.created_user = (auth_user_id, email, password, metadata)
        return auth_user_id

    async def invite_user(self, *, email: str, metadata: dict | None = None, redirect_to: str | None = None):
        auth_user_id = uuid4()
        self.invited_user = (auth_user_id, email, metadata, redirect_to)
        return auth_user_id

    async def update_user_password(self, auth_user_id, password: str) -> None:
        self.updated_password = (auth_user_id, password)

    async def delete_user(self, auth_user_id) -> None:
        self.deleted_user = auth_user_id


class FakeSessionStore:
    def __init__(self) -> None:
        self.created_sessions = []
        self.deleted_sessions = []

    async def create_session(
        self,
        *,
        auth_user_id,
        user_account_id,
        impersonator_auth_user_id=None,
        impersonator_user_account_id=None,
        ip_address,
        user_agent,
    ):
        self.created_sessions.append(
            {
                "auth_user_id": auth_user_id,
                "user_account_id": user_account_id,
                "impersonator_auth_user_id": impersonator_auth_user_id,
                "impersonator_user_account_id": impersonator_user_account_id,
                "ip_address": ip_address,
                "user_agent": user_agent,
            }
        )
        return WebSession(
            session_id="impersonated-session",
            auth_user_id=auth_user_id,
            user_account_id=user_account_id,
            expires_at=datetime(2026, 3, 19, 12, 0, tzinfo=UTC),
        )

    async def delete_session(self, session_id: str) -> None:
        self.deleted_sessions.append(session_id)


def _make_client(role: UserRole = UserRole.ADMIN) -> TestClient:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user(role))
    app.dependency_overrides[get_admin_accounts_service] = lambda: FakeAdminAccountsService()
    app.dependency_overrides[get_supabase_auth_gateway] = lambda: FakeSupabaseAuthGateway()
    return TestClient(app)


def test_admin_account_pages_render_for_admins() -> None:
    client = _make_client()

    list_response = client.get("/admin-accounts")
    new_response = client.get("/admin-accounts/new")
    detail_response = client.get("/admin-accounts/7")
    profile_response = client.get("/my-account")

    assert list_response.status_code == 200
    assert "Sample Admin" in list_response.text
    assert "Opprett admin-konto" in list_response.text
    assert "Filtrer på brukernavn, e-post eller visningsnavn" in list_response.text
    assert new_response.status_code == 200
    assert "Opprett admin-konto" in new_response.text
    assert "sette sitt eget passord" in new_response.text
    assert detail_response.status_code == 200
    assert "Lagre endringer" in detail_response.text
    assert "Logg inn som denne brukeren" in detail_response.text
    assert "2 gruppeadministrator-tilganger" in detail_response.text
    assert profile_response.status_code == 200
    assert "Min konto" in profile_response.text
    assert "Endre passord" in profile_response.text


def test_admin_account_pages_forbid_non_admins() -> None:
    client = _make_client(role=UserRole.VOLUNTEER)

    response = client.get("/admin-accounts")

    assert response.status_code == 403


def test_admin_account_pages_forbid_group_admins() -> None:
    client = _make_client(role=UserRole.GROUP_ADMIN)

    response = client.get("/admin-accounts")

    assert response.status_code == 403


def test_admin_account_create_redirects_and_calls_services() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    admin_accounts_service = FakeAdminAccountsService()
    supabase_auth_gateway = FakeSupabaseAuthGateway()
    app.dependency_overrides[get_admin_accounts_service] = lambda: admin_accounts_service
    app.dependency_overrides[get_supabase_auth_gateway] = lambda: supabase_auth_gateway
    client = TestClient(app)

    response = client.post(
        "/admin-accounts",
        data={
            "username": "new.admin",
            "email": "new.admin@example.test",
            "display_name": "New Admin",
            "role": "Admin",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin-accounts/11"
    assert supabase_auth_gateway.invited_user[1] == "new.admin@example.test"
    assert admin_accounts_service.created_account[1:] == (
        "new.admin",
        "new.admin@example.test",
        "New Admin",
        UserRole.ADMIN,
    )


def test_my_account_password_change_updates_password() -> None:
    app = create_app()
    current_user = make_authenticated_user()
    override_authenticated_user(app, current_user)
    app.dependency_overrides[get_admin_accounts_service] = lambda: FakeAdminAccountsService()
    supabase_auth_gateway = FakeSupabaseAuthGateway()
    supabase_auth_gateway.created_user = (current_user.auth_user_id, current_user.email, "", None)
    app.dependency_overrides[get_supabase_auth_gateway] = lambda: supabase_auth_gateway
    client = TestClient(app)

    response = client.post(
        "/my-account/password",
        data={
            "current_password": "CorrectPassword123",
            "new_password": "UpdatedPassword123",
            "confirm_password": "UpdatedPassword123",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/my-account?password_message=Passordet+ble+oppdatert."
    assert supabase_auth_gateway.updated_password == (current_user.auth_user_id, "UpdatedPassword123")


def test_admin_can_start_impersonation_from_admin_account() -> None:
    app = create_app()
    current_user = make_authenticated_user()
    override_authenticated_user(app, current_user)
    app.dependency_overrides[get_admin_accounts_service] = lambda: FakeAdminAccountsService()
    session_store = FakeSessionStore()
    app.dependency_overrides[get_session_store] = lambda: session_store
    client = TestClient(app)

    response = client.post("/admin-accounts/7/impersonate", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "kvarteret_session" in response.headers["set-cookie"]
    assert session_store.created_sessions[0]["user_account_id"] == 7
    assert session_store.created_sessions[0]["impersonator_user_account_id"] == current_user.user_account_id
