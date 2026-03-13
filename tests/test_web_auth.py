from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.login_service import LoginResult
from app.auth.models import AuthenticatedUser, WebSession
from app.auth.roles import UserRole
from app.main import create_app
from app.services.people import PersonListItem, PersonListPage


class FakeLoginService:
    async def login_with_bridge(self, *, identifier: str, password: str, ip_address: str | None, user_agent: str | None) -> LoginResult:
        return LoginResult(
            session=WebSession(
                session_id="session-123",
                auth_user_id=uuid4(),
                user_account_id=5,
                expires_at=datetime.now(UTC) + timedelta(hours=12),
            ),
            user=AuthenticatedUser(
                auth_user_id=uuid4(),
                user_account_id=5,
                username=identifier,
                email="admin.user@example.test",
                display_name="System User",
                role=UserRole.ADMIN,
            ),
            migrated_from_legacy=True,
        )


class FakeSessionStore:
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
                role=UserRole.ADMIN,
            ),
        )

    async def delete_session(self, session_id: str) -> None:
        return None


class FakePeopleService:
    async def list_people(self, query: str | None = None, limit: int = 50) -> list[PersonListItem]:
        return (await self.list_people_page(query=query, limit=limit, offset=0)).items

    async def list_people_page(self, query: str | None = None, limit: int = 10, offset: int = 0) -> PersonListPage:
        return PersonListPage(
            items=[
            PersonListItem(
                person_id=1,
                first_name="Sample",
                last_name="Person",
                full_name="Sample Person",
                email="person.one@example.test",
                phone="00000000",
                birth_date=date(1815, 12, 10),
                created_at=datetime.now(UTC),
                photo_url=None,
            )
            ],
            limit=limit,
            offset=offset,
            next_offset=None,
        )

    async def get_person_detail(self, person_id: int):
        return None


def test_login_sets_cookie_and_protected_page_renders() -> None:
    app = create_app()
    app.state.login_service = FakeLoginService()
    app.state.session_store = FakeSessionStore()
    app.state.people_service = FakePeopleService()
    client = TestClient(app)

    login_response = client.post(
        "/login",
        data={"identifier": "admin", "password": "Password123"},
        follow_redirects=False,
    )

    assert login_response.status_code == 303
    assert "kvarteret_session" in login_response.headers["set-cookie"]

    cookie_value = login_response.cookies.get("kvarteret_session")
    client.cookies.set("kvarteret_session", cookie_value)
    dashboard_response = client.get("/")
    people_response = client.get("/people")

    assert dashboard_response.status_code == 200
    assert "Logged in as" in dashboard_response.text
    assert people_response.status_code == 200
    assert "Sample Person" in people_response.text
