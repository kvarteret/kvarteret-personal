from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.dependencies import get_courses_service, get_groups_service, get_volunteer_search_service
from app.main import create_app
from app.domain.courses.service import CourseListItem
from app.domain.groups.service import GroupListItem
from app.domain.search import SearchQuery
from tests.support.helpers import make_authenticated_user, override_authenticated_user


class FakeGroupsService:
    async def list_groups(self, query: str | None = None, limit: int = 200):
        return [GroupListItem(7, "Bar", "Bar group", True, 20262, None, 2)]


class FakeCoursesService:
    async def list_courses(self, query: str | None = None, limit: int = 200):
        return [CourseListItem(4, "Fire safety", "Safety basics", datetime(2026, 3, 13, tzinfo=UTC))]


class FakeSearchService:
    def __init__(self) -> None:
        self.last_query: SearchQuery | None = None

    async def search_volunteers(self, query):
        self.last_query = query
        return [
            type(
                "Result",
                (),
                {
                    "volunteer_id": 12,
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
    search_service = FakeSearchService()
    app.dependency_overrides[get_volunteer_search_service] = lambda: search_service
    client = TestClient(app)

    response = client.get("/volunteers/search?include_groups=7&has_active_signed_contract=on")
    options_response = client.get("/volunteers/search/options/groups?field=include_groups&selected=7")

    assert response.status_code == 200
    assert "Avansert søk" in response.text
    assert "Sample Person" in response.text
    assert "Kun aktive frivillige med signert kontrakt" in response.text
    assert 'name="has_active_signed_contract" type="checkbox" value="on" checked' in response.text
    assert search_service.last_query is not None
    assert search_service.last_query.has_active_signed_contract is True
    assert options_response.status_code == 200
    assert "Bar" in options_response.text


def test_search_page_accepts_checkbox_style_contract_filter_value() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_groups_service] = lambda: FakeGroupsService()
    app.dependency_overrides[get_courses_service] = lambda: FakeCoursesService()
    search_service = FakeSearchService()
    app.dependency_overrides[get_volunteer_search_service] = lambda: search_service
    client = TestClient(app)

    response = client.get("/volunteers/search?has_active_signed_contract=on")

    assert response.status_code == 200
    assert search_service.last_query is not None
    assert search_service.last_query.has_active_signed_contract is True


def test_search_filter_options_ignore_invalid_selected_ids() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_groups_service] = lambda: FakeGroupsService()
    app.dependency_overrides[get_courses_service] = lambda: FakeCoursesService()
    app.dependency_overrides[get_volunteer_search_service] = lambda: FakeSearchService()
    client = TestClient(app)

    response = client.get("/volunteers/search/options/groups?field=include_groups&selected=7,not-a-number,9")

    assert response.status_code == 200
    assert "Bar" in response.text


def test_search_page_accepts_blank_numeric_fields() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_groups_service] = lambda: FakeGroupsService()
    app.dependency_overrides[get_courses_service] = lambda: FakeCoursesService()
    search_service = FakeSearchService()
    app.dependency_overrides[get_volunteer_search_service] = lambda: search_service
    client = TestClient(app)

    response = client.get(
        "/volunteers/search?birth_date_after=&birth_date_before=&pingvin_points_above=&pingvin_points_below="
    )

    assert response.status_code == 200
    assert search_service.last_query is not None
    assert "Sample Person" in response.text
