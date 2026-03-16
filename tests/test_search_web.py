from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.dependencies import get_courses_service, get_groups_service, get_search_service
from app.main import create_app
from app.services.courses import CourseListItem
from app.services.groups import GroupListItem
from tests.helpers import make_authenticated_user, override_authenticated_user


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
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_groups_service] = lambda: FakeGroupsService()
    app.dependency_overrides[get_courses_service] = lambda: FakeCoursesService()
    app.dependency_overrides[get_search_service] = lambda: FakeSearchService()
    client = TestClient(app)

    response = client.get("/search?include_groups=7")
    options_response = client.get("/search/options/groups?field=include_groups&selected=7")

    assert response.status_code == 200
    assert "Avansert søk" in response.text
    assert "Sample Person" in response.text
    assert options_response.status_code == 200
    assert "Bar" in options_response.text
