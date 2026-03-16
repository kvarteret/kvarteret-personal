from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.dependencies import get_courses_service, get_groups_service, get_semester_transfer_service
from app.main import create_app
from app.services.courses import CourseCompletionItem, CourseDetail, CourseListItem, RequiredGroupItem
from app.services.groups import GroupDetail, GroupListItem, GroupMemberItem, GroupPositionItem
from app.services.semester_transfer import SemesterTransferCandidate, SemesterTransferPreview
from tests.helpers import make_authenticated_user, override_authenticated_user


class FakeGroupsService:
    async def list_groups(self, query: str | None = None, limit: int = 100) -> list[GroupListItem]:
        return [GroupListItem(7, "Bar", "Bar group", True, 20262, None, 2)]

    async def get_group_detail(self, group_id: int) -> GroupDetail | None:
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
        return [CourseListItem(4, "Fire safety", "Safety basics", datetime(2026, 3, 13, tzinfo=UTC))]

    async def get_course_detail(self, course_id: int) -> CourseDetail | None:
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


def test_groups_and_courses_pages_render() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_groups_service] = lambda: FakeGroupsService()
    app.dependency_overrides[get_courses_service] = lambda: FakeCoursesService()
    app.dependency_overrides[get_semester_transfer_service] = lambda: FakeSemesterTransferService()
    client = TestClient(app)

    groups_response = client.get("/groups")
    group_detail_response = client.get("/groups/7")
    semester_transfer_response = client.get("/groups/7/semester-transfer")
    courses_response = client.get("/courses")
    course_detail_response = client.get("/courses/4")

    assert groups_response.status_code == 200
    assert "Bar group" in groups_response.text
    assert group_detail_response.status_code == 200
    assert "Siste gruppehistorikk" in group_detail_response.text
    assert semester_transfer_response.status_code == 200
    assert "Kopier medlemmer fra Spring 2026 til" in semester_transfer_response.text
    assert courses_response.status_code == 200
    assert "Fire safety" in courses_response.text
    assert course_detail_response.status_code == 200
    assert "Siste fullføringer" in course_detail_response.text
