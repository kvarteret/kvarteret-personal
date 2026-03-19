from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.login_service import LoginResult
from app.auth.models import WebSession
from app.auth.roles import UserRole
from app.dependencies import (
    get_current_user,
    get_login_service,
    get_session_store,
    get_volunteers_service,
    require_authenticated_user,
)
from app.main import create_app
from app.runtime import build_application_container
from app.services.volunteers import VolunteerListItem, VolunteerListPage
from tests.helpers import make_authenticated_user


class FakeLoginService:
    async def login_with_bridge(self, *, identifier: str, password: str, ip_address: str | None, user_agent: str | None) -> LoginResult:
        return LoginResult(
            session=type(
                "Session",
                (),
                {
                    "session_id": "session-123",
                    "auth_user_id": uuid4(),
                    "user_account_id": 5,
                    "expires_at": datetime.now(UTC),
                },
            )(),
            user=make_authenticated_user(UserRole.ADMIN),
            migrated_from_legacy=True,
        )


class FakeVolunteersService:
    async def list_volunteers(self, query: str | None = None, limit: int = 50) -> list[VolunteerListItem]:
        return (await self.list_volunteers_page(query=query, limit=limit, cursor=None)).items

    async def list_volunteers_page(self, query: str | None = None, limit: int = 10, cursor: str | None = None) -> VolunteerListPage:
        return VolunteerListPage(
            items=[
                VolunteerListItem(
                    volunteer_id=1,
                    first_name="Sample",
                    last_name="Person",
                    full_name="Sample Person",
                    email="person.one@example.test",
                    phone="00000000",
                    photo_url=None,
                )
            ],
            limit=limit,
            cursor=cursor,
            next_cursor=None,
        )

    async def get_volunteer_detail(self, volunteer_id: int):
        return None

    async def list_role_assignments(self, volunteer_id: int, limit: int = 12):
        return []

    async def list_volunteer_documents(self, volunteer_id: int):
        return []

    async def get_volunteer_relations(self, volunteer_id: int):
        return None


class FakeSessionStore:
    async def load_authenticated_user(self, session_id: str):
        return None


class MiddlewareSessionStore:
    def __init__(self, user) -> None:
        self.user = user

    async def load_authenticated_user(self, session_id: str):
        return (
            WebSession(
                session_id=session_id,
                auth_user_id=self.user.auth_user_id,
                user_account_id=self.user.user_account_id,
                expires_at=datetime.now(UTC),
            ),
            self.user,
        )


class ImpersonatedSessionStore:
    def __init__(self, user, impersonator_user) -> None:
        self.user = user
        self.impersonator_user = impersonator_user
        self.created_sessions = []
        self.deleted_sessions = []

    async def load_authenticated_user(self, session_id: str):
        return (
            WebSession(
                session_id=session_id,
                auth_user_id=self.user.auth_user_id,
                user_account_id=self.user.user_account_id,
                expires_at=datetime.now(UTC),
                impersonator_user=self.impersonator_user,
            ),
            self.user,
        )

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
            }
        )
        return WebSession(
            session_id="restored-admin-session",
            auth_user_id=auth_user_id,
            user_account_id=user_account_id,
            expires_at=datetime.now(UTC),
        )

    async def delete_session(self, session_id: str) -> None:
        self.deleted_sessions.append(session_id)


class FakePendingVolunteerApplicationsService:
    def __init__(self) -> None:
        self.calls = 0

    async def count_pending_volunteer_applications(self) -> int:
        self.calls += 1
        return 3


def test_login_sets_cookie_and_protected_page_renders() -> None:
    app = create_app()
    user = make_authenticated_user(UserRole.ADMIN)
    app.dependency_overrides[get_login_service] = lambda: FakeLoginService()
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_session_store] = lambda: FakeSessionStore()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_authenticated_user] = lambda: user
    client = TestClient(app)

    login_response = client.post(
        "/login",
        data={"identifier": "admin", "password": "Password123"},
        follow_redirects=False,
    )

    assert login_response.status_code == 303
    assert "kvarteret_session" in login_response.headers["set-cookie"]

    dashboard_response = client.get("/")
    people_response = client.get("/volunteers")

    assert dashboard_response.status_code == 200
    assert "Admin-kontoer" in dashboard_response.text
    assert "Registreringer" in dashboard_response.text
    assert people_response.status_code == 200
    assert "Sample Person" in people_response.text
    assert "Ny frivillig" in people_response.text


def test_container_backed_auth_middleware_populates_current_user_and_pending_count() -> None:
    user = make_authenticated_user(UserRole.ADMIN)
    container = build_application_container()
    container.session_store = MiddlewareSessionStore(user)
    pending_service = FakePendingVolunteerApplicationsService()
    container.volunteer_applications_service = pending_service  # type: ignore[assignment]
    app = create_app(container=container)
    client = TestClient(app)

    response = client.get(
        "/",
        cookies={
            container.settings.session_cookie_name: container.session_cookie_signer.sign_session_id("session-123"),
        },
    )

    assert response.status_code == 200
    assert "Admin-kontoer" in response.text
    assert "Registreringer" in response.text
    assert ">3<" in response.text
    assert pending_service.calls == 1


def test_container_backed_auth_middleware_skips_pending_count_for_htmx_fragments() -> None:
    user = make_authenticated_user(UserRole.ADMIN)
    container = build_application_container()
    container.session_store = MiddlewareSessionStore(user)
    pending_service = FakePendingVolunteerApplicationsService()
    container.volunteer_applications_service = pending_service  # type: ignore[assignment]
    container.volunteers_service = FakeVolunteersService()  # type: ignore[assignment]
    app = create_app(container=container)
    client = TestClient(app)

    response = client.get(
        "/volunteers/list",
        headers={"HX-Request": "true"},
        cookies={
            container.settings.session_cookie_name: container.session_cookie_signer.sign_session_id("session-123"),
        },
    )

    assert response.status_code == 200
    assert "Sample Person" in response.text
    assert pending_service.calls == 0


def test_container_backed_auth_middleware_renders_impersonation_banner() -> None:
    impersonated_user = make_authenticated_user(UserRole.VOLUNTEER)
    admin_user = make_authenticated_user(UserRole.ADMIN)
    container = build_application_container()
    container.session_store = ImpersonatedSessionStore(impersonated_user, admin_user)
    app = create_app(container=container)
    client = TestClient(app)

    response = client.get(
        "/",
        cookies={
            container.settings.session_cookie_name: container.session_cookie_signer.sign_session_id("session-123"),
        },
    )

    assert response.status_code == 200
    assert "Impersonering aktiv" in response.text
    assert "Avslutt impersonering" in response.text


def test_stop_impersonation_restores_admin_session() -> None:
    impersonated_user = make_authenticated_user(UserRole.VOLUNTEER)
    admin_user = make_authenticated_user(UserRole.ADMIN)
    container = build_application_container()
    session_store = ImpersonatedSessionStore(impersonated_user, admin_user)
    container.session_store = session_store
    app = create_app(container=container)
    client = TestClient(app)

    response = client.post(
        "/impersonation/stop",
        cookies={
            container.settings.session_cookie_name: container.session_cookie_signer.sign_session_id("session-123"),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "kvarteret_session" in response.headers["set-cookie"]
    assert session_store.created_sessions == [
        {
            "auth_user_id": admin_user.auth_user_id,
            "user_account_id": admin_user.user_account_id,
            "impersonator_auth_user_id": None,
            "impersonator_user_account_id": None,
        }
    ]
    assert session_store.deleted_sessions == ["session-123"]


def test_protected_web_page_redirects_to_login_when_unauthenticated() -> None:
    client = TestClient(create_app())

    response = client.get("/volunteers", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_protected_htmx_fragment_redirects_to_login_when_unauthenticated() -> None:
    client = TestClient(create_app())

    response = client.get("/volunteers/list", headers={"HX-Request": "true"}, follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/login"
