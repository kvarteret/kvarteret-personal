from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.login_service import LoginResult
from app.auth.roles import UserRole
from app.dependencies import get_current_user, get_login_service, get_people_service, get_session_store, require_authenticated_user
from app.main import create_app
from app.services.people import PersonListItem, PersonListPage
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


class FakeSessionStore:
    async def load_authenticated_user(self, session_id: str):
        return None


def test_login_sets_cookie_and_protected_page_renders() -> None:
    app = create_app()
    user = make_authenticated_user(UserRole.ADMIN)
    app.dependency_overrides[get_login_service] = lambda: FakeLoginService()
    app.dependency_overrides[get_people_service] = lambda: FakePeopleService()
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
    people_response = client.get("/people")

    assert dashboard_response.status_code == 200
    assert "Logged in as" in dashboard_response.text
    assert people_response.status_code == 200
    assert "Sample Person" in people_response.text
