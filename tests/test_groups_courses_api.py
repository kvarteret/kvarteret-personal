from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.cookies import sign_session_id
from app.auth.models import AuthenticatedUser, WebSession
from app.auth.roles import UserRole
from app.main import create_app
from app.services.courses import CourseCompletionItem, CourseDetail, CourseListItem, RequiredGroupItem
from app.services.groups import GroupDetail, GroupListItem, GroupMemberItem, GroupPositionItem
from app.services.semester_transfer import SemesterTransferCandidate, SemesterTransferPreview


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
    async def list_groups(self, query: str | None = None, limit: int = 100) -> list[GroupListItem]:
        return [
            GroupListItem(
                group_id=7,
                name="Bar",
                description="Bar group",
                active=True,
                active_until_semester=20262,
                parent_group_id=None,
                discount_step=2,
            )
        ]

    async def get_group_detail(self, group_id: int) -> GroupDetail | None:
        if group_id != 7:
            return None
        return GroupDetail(
            group_id=7,
            name="Bar",
            description="Bar group",
            active=True,
            active_until_semester=20262,
            active_until_label="Fall 2026",
            parent_group_id=None,
            discount_step=2,
            created_at=datetime(2026, 3, 13, tzinfo=UTC),
            positions=[GroupPositionItem(role_id=3, role_name="Shift lead", pingvin_points=4)],
            recent_members=[
                GroupMemberItem(
                    history_id=9,
                    person_id=12,
                    person_name="Sample Person",
                    role_name="Shift lead",
                    semester_code=20262,
                    semester_label="Fall 2026",
                    contract_signed=True,
                )
            ],
        )


class FakeCoursesService:
    async def list_courses(self, query: str | None = None, limit: int = 100) -> list[CourseListItem]:
        return [
            CourseListItem(
                course_id=4,
                name="Fire safety",
                description="Safety basics",
                created_at=datetime(2026, 3, 13, tzinfo=UTC),
            )
        ]

    async def get_course_detail(self, course_id: int) -> CourseDetail | None:
        if course_id != 4:
            return None
        return CourseDetail(
            course_id=4,
            name="Fire safety",
            description="Safety basics",
            created_at=datetime(2026, 3, 13, tzinfo=UTC),
            required_groups=[RequiredGroupItem(group_id=7, group_name="Bar")],
            recent_completions=[
                CourseCompletionItem(
                    completion_id=11,
                    person_id=12,
                    person_name="Sample Person",
                    completed_semester_code=20262,
                    completed_semester_label="Fall 2026",
                )
            ],
        )


class FakeSemesterTransferService:
    async def preview_transfer(self, group_id: int, source_semester: int | None = None, target_semester: int | None = None):
        return SemesterTransferPreview(
            group_id=7,
            group_name="Bar",
            source_semester=20261,
            source_semester_label="Spring 2026",
            target_semester=20262,
            target_semester_label="Fall 2026",
            candidates=[
                SemesterTransferCandidate(
                    person_id=12,
                    person_name="Sample Person",
                    role_id=3,
                    role_name="Shift lead",
                    contract_signed=False,
                    source_history_id=9,
                )
            ],
        )

    async def apply_transfer(self, group_id: int, target_semester: int, entries):
        return 1


def _make_client() -> TestClient:
    app = create_app()
    app.state.session_store = FakeSessionStore()
    app.state.groups_service = FakeGroupsService()
    app.state.courses_service = FakeCoursesService()
    app.state.semester_transfer_service = FakeSemesterTransferService()
    client = TestClient(app)
    client.cookies.set("kvarteret_session", sign_session_id("session-123"))
    return client


def test_groups_api_returns_list_and_detail() -> None:
    client = _make_client()

    list_response = client.get("/api/v1/groups")
    detail_response = client.get("/api/v1/groups/7")

    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "Bar"
    assert detail_response.status_code == 200
    assert detail_response.json()["recent_members"][0]["person_name"] == "Sample Person"


def test_courses_api_returns_list_and_detail() -> None:
    client = _make_client()

    list_response = client.get("/api/v1/courses")
    detail_response = client.get("/api/v1/courses/4")

    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "Fire safety"
    assert detail_response.status_code == 200
    assert detail_response.json()["required_groups"][0]["group_name"] == "Bar"


def test_groups_api_exposes_semester_transfer_preview_and_apply() -> None:
    client = _make_client()

    preview_response = client.get("/api/v1/groups/7/semester-transfer")
    apply_response = client.post(
        "/api/v1/groups/7/semester-transfer",
        json={"target_semester": 20262, "entries": [{"person_id": 12, "role_id": 3}]},
    )

    assert preview_response.status_code == 200
    assert preview_response.json()["candidates"][0]["person_name"] == "Sample Person"
    assert apply_response.status_code == 200
    assert apply_response.json()["inserted_count"] == 1
