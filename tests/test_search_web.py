from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.cookies import sign_session_id
from app.auth.models import AuthenticatedUser, WebSession
from app.auth.roles import UserRole
from app.main import create_app
from app.services.courses import CourseListItem
from app.services.groups import GroupListItem


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


class FakeGroupsService:
    async def list_groups(self, query: str | None = None, limit: int = 200):
        return [GroupListItem(7, "Bar", "Bar group", True, 20262, None, 2)]


class FakeCoursesService:
    async def list_courses(self, query: str | None = None, limit: int = 200):
        return [CourseListItem(4, "Fire safety", "Safety basics", datetime(2026, 3, 13, tzinfo=UTC))]


class FakeSearchService:
    async def search_people(self, query):
        return [
            type(
                "Result",
                (),
                {
                    "person_id": 12,
                    "full_name": "Sample Person",
                    "email": "person.one@example.test",
                    "phone": "00000000",
                    "pingvin_points": 8,
                    "last_semester_label": "Fall 2026",
                },
            )()
        ]


def test_search_page_renders_with_fake_services() -> None:
    app = create_app()
    app.state.session_store = FakeSessionStore()
    app.state.groups_service = FakeGroupsService()
    app.state.courses_service = FakeCoursesService()
    app.state.search_service = FakeSearchService()
    client = TestClient(app)
    client.cookies.set("kvarteret_session", sign_session_id("session-123"))

    response = client.get("/search?include_groups=7")

    assert response.status_code == 200
    assert "Advanced search" in response.text
    assert "Sample Person" in response.text
    assert "Bar" in response.text
