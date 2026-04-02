from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.auth.roles import UserRole
from app.dependencies import get_courses_service, get_groups_service, get_volunteers_service
from app.main import create_app
from app.domain.courses.service import CourseListItem
from app.domain.groups.service import GroupBreakdownItem, GroupMemberCount, OrgSemesterDetailed, SemesterRetentionStats
from app.domain.volunteers.models import (
    CardItem,
    CourseCompletionNotFoundError,
    DuplicateCourseCompletionError,
    DocumentItem,
    GroupOption,
    InvalidCourseCompletionError,
    RoleAssignmentItem,
    NextOfKinItem,
    VolunteerCourseCompletionItem,
    VolunteerDetail,
    VolunteerListItem,
    VolunteerListPage,
    VolunteerRelations,
    AssignmentRoleOption,
)
from tests.support.helpers import make_authenticated_user, override_authenticated_user


class FakeVolunteersService:
    def __init__(self) -> None:
        self.updated_profile_calls: list[dict[str, object | None]] = []
        self.updated_relations_calls: list[dict[str, object]] = []
        self.created_course_completion_calls: list[dict[str, int]] = []
        self.deleted_course_completion_calls: list[dict[str, int]] = []
        self.updated_role_assignment_calls: list[dict[str, int | bool]] = []
        self.uploaded_photo_calls: list[dict[str, str | int | None]] = []
        self.deleted_photo_calls: list[int] = []
        self.deleted_volunteer_calls: list[int] = []

    async def list_volunteers(self, query: str | None = None, limit: int = 50) -> list[VolunteerListItem]:
        return (await self.list_volunteers_page(query=query, limit=limit, cursor=None)).items

    async def list_volunteers_page(self, query: str | None = None, limit: int = 10, cursor: str | None = None) -> VolunteerListPage:
        return VolunteerListPage(
            items=[
                VolunteerListItem(
                    volunteer_id=12,
                    first_name="Sample",
                    last_name="Person",
                    full_name="Sample Person",
                    email="person.one@example.test",
                    phone="00000000",
                    photo_url="/media/photos/abc123.jpg?token=test",
                )
            ],
            limit=limit,
            cursor=cursor,
            next_cursor="cursor-2" if cursor is None else None,
        )

    async def get_volunteer_detail(self, volunteer_id: int) -> VolunteerDetail | None:
        if volunteer_id != 12:
            return None
        return VolunteerDetail(
            volunteer_id=12,
            first_name="Sample",
            last_name="Person",
            full_name="Sample Person",
            email="person.one@example.test",
            phone="00000000",
            birth_date=date(1815, 12, 10),
            created_at=datetime(2026, 3, 13, tzinfo=UTC),
            gender_code="K",
            gender_label="Kvinne",
            address="Example address",
            postal_code="0000",
            pingvin_points=8,
            photo_url="/media/photos/abc123.jpg?token=test",
        )

    async def list_role_assignments(self, volunteer_id: int, limit: int = 12) -> list[RoleAssignmentItem]:
        return [
            RoleAssignmentItem(
                history_id=5,
                group_id=9,
                group_name="Bar",
                role_id=2,
                role_name="Shift lead",
                pingvin_points=4,
                semester_code=20262,
                semester_label="Fall 2026",
                contract_signed=True,
            )
        ]

    async def list_course_completions(
        self,
        volunteer_id: int,
        limit: int = 100,
    ) -> list[VolunteerCourseCompletionItem]:
        return [
            VolunteerCourseCompletionItem(
                completion_id=11,
                course_id=4,
                course_name="Fire safety",
                completed_semester_code=20262,
                completed_semester_label="Fall 2026",
            )
        ]

    async def list_volunteer_documents(self, volunteer_id: int) -> list[DocumentItem]:
        return [
            DocumentItem(
                document_id=6,
                filename="certificate.pdf",
                filetype="pdf",
                group_id=7,
                created_at=datetime(2026, 3, 13, tzinfo=UTC),
                storage_path="12/certificate.pdf",
                download_url=None,
            )
        ]

    async def get_volunteer_relations(self, volunteer_id: int) -> VolunteerRelations:
        return VolunteerRelations(
            next_of_kin=[NextOfKinItem(next_of_kin_id=1, name="Contact Person", phone="00000001")],
            cards=[CardItem(card_id=3, card_number="CARD-42")],
        )

    async def list_assignment_groups(self) -> list[GroupOption]:
        return [GroupOption(group_id=9, name="Bar", active=True)]

    async def list_assignment_roles(self, group_id: int) -> list[AssignmentRoleOption]:
        return [AssignmentRoleOption(role_id=2, group_id=group_id, role_name="Shift lead", pingvin_points=4)]

    async def update_volunteer_profile(
        self,
        *,
        volunteer_id: int,
        first_name: str | None,
        last_name: str,
        email: str | None,
        phone: str | None,
        birth_date,
        gender_code: str,
        address: str | None,
        postal_code: str | None,
    ) -> VolunteerDetail:
        self.updated_profile_calls.append(
            {
                "volunteer_id": volunteer_id,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": phone,
                "birth_date": birth_date,
                "gender_code": gender_code,
                "address": address,
                "postal_code": postal_code,
            }
        )
        detail = await self.get_volunteer_detail(volunteer_id)
        assert detail is not None
        return detail

    async def replace_volunteer_relations(
        self,
        *,
        volunteer_id: int,
        card_numbers: list[str],
        next_of_kin: list[tuple[str, str]],
    ) -> VolunteerRelations:
        self.updated_relations_calls.append(
            {
                "volunteer_id": volunteer_id,
                "card_numbers": card_numbers,
                "next_of_kin": next_of_kin,
            }
        )
        return await self.get_volunteer_relations(volunteer_id)

    async def add_course_completion(
        self,
        *,
        volunteer_id: int,
        course_id: int,
        year: int,
        term: int,
    ) -> None:
        if course_id == 999:
            raise InvalidCourseCompletionError("Selected course was not found.")
        if course_id == 4 and year == 2026 and term == 2:
            raise DuplicateCourseCompletionError("Dette kurset er allerede registrert for valgt semester.")
        self.created_course_completion_calls.append(
            {
                "volunteer_id": volunteer_id,
                "course_id": course_id,
                "year": year,
                "term": term,
            }
        )

    async def delete_course_completion_for_volunteer(self, volunteer_id: int, completion_id: int) -> None:
        if completion_id != 11:
            raise CourseCompletionNotFoundError(f"Course completion {completion_id} was not found.")
        self.deleted_course_completion_calls.append(
            {
                "volunteer_id": volunteer_id,
                "completion_id": completion_id,
            }
        )

    async def update_role_assignment_for_volunteer(
        self,
        volunteer_id: int,
        history_id: int,
        *,
        group_id: int,
        role_id: int,
        year: int,
        term: int,
        contract_signed: bool,
    ) -> None:
        self.updated_role_assignment_calls.append(
            {
                "volunteer_id": volunteer_id,
                "history_id": history_id,
                "group_id": group_id,
                "role_id": role_id,
                "year": year,
                "term": term,
                "contract_signed": contract_signed,
            }
        )

    async def upload_photo(self, volunteer_id: int, filename: str, content: bytes, content_type: str | None) -> None:
        self.uploaded_photo_calls.append(
            {
                "volunteer_id": volunteer_id,
                "filename": filename,
                "content_type": content_type,
                "content_length": len(content),
            }
        )

    async def delete_photo(self, volunteer_id: int) -> None:
        self.deleted_photo_calls.append(volunteer_id)

    async def delete_volunteer(self, volunteer_id: int) -> None:
        self.deleted_volunteer_calls.append(volunteer_id)


class FakeGroupsService:
    async def get_org_stats_detailed(self) -> list[OrgSemesterDetailed]:
        return [
            OrgSemesterDetailed(
                semester_code=20262,
                semester_label="Fall 2026",
                unique_members=120,
                groups=[GroupBreakdownItem(group_name="Bar", member_count=14)],
            )
        ]

    async def get_current_group_member_counts(self) -> list[GroupMemberCount]:
        return [GroupMemberCount(group_id=9, group_name="Bar", member_count=14)]

    async def get_org_retention_stats(self) -> list[SemesterRetentionStats]:
        return [
            SemesterRetentionStats(
                semester_code=20261,
                semester_label="Spring 2026",
                total_members=11,
                retained_from_prev=7,
                new_members=4,
                retained_to_next_same_group=5,
                retained_to_next_other_group=3,
                retained_to_next=8,
                churned=3,
            ),
            SemesterRetentionStats(
                semester_code=20262,
                semester_label="Fall 2026",
                total_members=14,
                retained_from_prev=8,
                new_members=6,
                retained_to_next_same_group=0,
                retained_to_next_other_group=0,
                retained_to_next=0,
                churned=14,
            ),
        ]


class FakeCoursesService:
    async def list_courses(self, query: str | None = None, limit: int = 100) -> list[CourseListItem]:
        return [CourseListItem(4, "Fire safety", "Safety basics", datetime(2026, 3, 13, tzinfo=UTC))]

    async def get_current_group_member_counts(self) -> list[GroupMemberCount]:
        return [GroupMemberCount(group_id=9, group_name="Bar", member_count=14)]

    async def get_org_retention_stats(self) -> list[SemesterRetentionStats]:
        return [
            SemesterRetentionStats(
                semester_code=20261,
                semester_label="Spring 2026",
                total_members=11,
                retained_from_prev=7,
                new_members=4,
                retained_to_next_same_group=5,
                retained_to_next_other_group=3,
                retained_to_next=8,
                churned=3,
            ),
            SemesterRetentionStats(
                semester_code=20262,
                semester_label="Fall 2026",
                total_members=14,
                retained_from_prev=8,
                new_members=6,
                retained_to_next_same_group=0,
                retained_to_next_other_group=0,
                retained_to_next=0,
                churned=14,
            ),
        ]


def test_volunteer_pages_render_with_fake_service() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_groups_service] = lambda: FakeGroupsService()
    app.dependency_overrides[get_courses_service] = lambda: FakeCoursesService()
    client = TestClient(app)

    list_response = client.get("/volunteers")
    detail_response = client.get("/volunteers/12")

    assert list_response.status_code == 200
    assert "Sample Person" in list_response.text
    assert "Filtrer på navn" in list_response.text
    assert 'href="/volunteers/stats"' in list_response.text
    assert 'hx-trigger="keyup changed delay:300ms, search"' in list_response.text
    assert 'id="volunteer-search-indicator"' in list_response.text
    assert "Laster flere frivillige" in list_response.text
    assert detail_response.status_code == 200
    assert detail_response.headers["cache-control"] == "no-store"
    assert "Laster historikk" in detail_response.text
    assert "Laster kurs" in detail_response.text
    assert "Laster filer" in detail_response.text
    assert "Laster kort og pårørende" in detail_response.text
    assert "name=\"gender\"" in detail_response.text
    assert 'type="file"' in detail_response.text
    assert 'enctype="multipart/form-data"' in detail_response.text
    assert 'id="volunteer-photo-input"' in detail_response.text
    assert 'onchange="this.form.submit()"' in detail_response.text
    assert 'src="/media/photos/abc123.jpg?token=test"' in detail_response.text
    assert 'class="grid h-52 w-52 cursor-pointer place-items-center overflow-hidden rounded-sm bg-stone-300 text-5xl font-semibold text-stone-600 shadow-md transition hover:shadow-lg"' in detail_response.text
    assert 'hx-trigger="intersect once"' in detail_response.text
    assert "Slett frivillig" in detail_response.text


def test_management_user_can_delete_volunteer() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user(UserRole.GROUP_ADMIN))
    volunteers_service = FakeVolunteersService()
    app.dependency_overrides[get_volunteers_service] = lambda: volunteers_service
    client = TestClient(app)

    response = client.post("/volunteers/12?_method=DELETE", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/volunteers"
    assert volunteers_service.deleted_volunteer_calls == [12]


def test_group_admin_can_upload_photo_for_volunteer_in_their_group() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user(UserRole.GROUP_ADMIN))
    volunteers_service = FakeVolunteersService()
    app.dependency_overrides[get_volunteers_service] = lambda: volunteers_service
    client = TestClient(app)

    detail_response = client.get("/volunteers/12")
    upload_response = client.post(
        "/volunteers/12/photo",
        files={"photo": ("avatar.png", b"fake-image", "image/png")},
        follow_redirects=False,
    )

    assert detail_response.status_code == 200
    assert 'type="file"' in detail_response.text
    assert 'title="Klikk for å endre profilbilde"' in detail_response.text
    assert upload_response.status_code == 303
    assert upload_response.headers["location"] == "/volunteers/12"
    assert volunteers_service.uploaded_photo_calls == [
        {
            "volunteer_id": 12,
            "filename": "avatar.png",
            "content_type": "image/png",
            "content_length": 10,
        }
    ]


def test_group_admin_can_update_profile_for_any_volunteer() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user(UserRole.GROUP_ADMIN))
    volunteers_service = FakeVolunteersService()
    app.dependency_overrides[get_volunteers_service] = lambda: volunteers_service
    client = TestClient(app)

    detail_response = client.get("/volunteers/12")
    update_response = client.post(
        "/volunteers/12?_method=PATCH",
        data={
            "first_name": "Updated",
            "last_name": "Person",
            "email": "updated@example.test",
            "phone": "12345678",
            "birth_date": "1815-12-10",
            "gender": "K",
            "address": "Updated address",
            "postal_code": "5000",
        },
        follow_redirects=False,
    )

    assert detail_response.status_code == 200
    assert 'name="gender"' in detail_response.text
    assert update_response.status_code == 303
    assert update_response.headers["location"] == "/volunteers/12"
    assert volunteers_service.updated_profile_calls == [
        {
            "volunteer_id": 12,
            "first_name": "Updated",
            "last_name": "Person",
            "email": "updated@example.test",
            "phone": "12345678",
            "birth_date": date(1815, 12, 10),
            "gender_code": "K",
            "address": "Updated address",
            "postal_code": "5000",
        }
    ]


def test_group_admin_can_upload_photo_for_any_volunteer() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user(UserRole.GROUP_ADMIN))
    volunteers_service = FakeVolunteersService()
    app.dependency_overrides[get_volunteers_service] = lambda: volunteers_service
    client = TestClient(app)

    detail_response = client.get("/volunteers/12")
    upload_response = client.post(
        "/volunteers/12/photo",
        files={"photo": ("avatar.png", b"fake-image", "image/png")},
        follow_redirects=False,
    )

    assert detail_response.status_code == 200
    assert 'type="file"' in detail_response.text
    assert upload_response.status_code == 303
    assert volunteers_service.uploaded_photo_calls == [
        {
            "volunteer_id": 12,
            "filename": "avatar.png",
            "content_type": "image/png",
            "content_length": 10,
        }
    ]


def test_group_admin_photo_upload_rejects_files_over_40mb() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user(UserRole.GROUP_ADMIN))
    volunteers_service = FakeVolunteersService()
    app.dependency_overrides[get_volunteers_service] = lambda: volunteers_service
    client = TestClient(app)

    response = client.post(
        "/volunteers/12/photo",
        files={"photo": ("avatar.png", b"x" * (40 * 1024 * 1024 + 1), "image/png")},
        follow_redirects=False,
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Photos must be 40 MB or smaller."}
    assert volunteers_service.uploaded_photo_calls == []


def test_group_admin_can_update_profile_for_any_volunteer_even_without_shared_group() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user(UserRole.GROUP_ADMIN))
    volunteers_service = FakeVolunteersService()
    app.dependency_overrides[get_volunteers_service] = lambda: volunteers_service
    client = TestClient(app)

    detail_response = client.get("/volunteers/12")
    update_response = client.post(
        "/volunteers/12?_method=PATCH",
        data={
            "first_name": "Updated",
            "last_name": "Person",
            "gender": "K",
        },
        follow_redirects=False,
    )

    assert detail_response.status_code == 200
    assert 'name="gender"' in detail_response.text
    assert update_response.status_code == 303
    assert volunteers_service.updated_profile_calls == [
        {
            "volunteer_id": 12,
            "first_name": "Updated",
            "last_name": "Person",
            "email": None,
            "phone": None,
            "birth_date": None,
            "gender_code": "K",
            "address": None,
            "postal_code": None,
        }
    ]


def test_volunteer_list_fragment_renders_with_fake_service() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_groups_service] = lambda: FakeGroupsService()
    client = TestClient(app)

    response = client.get("/volunteers/list?q=sample")

    assert response.status_code == 200
    assert "Sample Person" in response.text
    assert "<!DOCTYPE html>" not in response.text


def test_volunteer_html_responses_are_browser_cacheable_for_htmx_preload() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_groups_service] = lambda: FakeGroupsService()
    client = TestClient(app)

    page_response = client.get("/volunteers")
    partial_response = client.get("/volunteers/list?q=sample")

    assert page_response.headers["cache-control"] == "private, max-age=60"
    assert partial_response.headers["cache-control"] == "private, max-age=60"
    assert page_response.headers["vary"] == "Cookie, HX-Boosted, HX-Request"
    assert partial_response.headers["vary"] == "Cookie, HX-Boosted, HX-Request"


def test_volunteer_detail_panels_render_with_fake_service() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_groups_service] = lambda: FakeGroupsService()
    client = TestClient(app)

    history_response = client.get("/volunteers/12/role-assignments/panel")
    documents_response = client.get("/volunteers/12/documents/panel")
    relations_response = client.get("/volunteers/12/relations/panel")

    assert history_response.status_code == 200
    assert "Shift lead" in history_response.text
    assert "Legg til nytt verv" in history_response.text
    assert "Velg gruppe" in history_response.text
    assert "Rediger" in history_response.text
    assert "Slett" in history_response.text
    assert "kontrakt" in history_response.text
    assert 'href="/groups/9"' in history_response.text
    assert documents_response.status_code == 200
    assert "certificate.pdf" in documents_response.text
    assert "Last opp fil" not in documents_response.text
    assert "window.confirm('Slette denne filen?')" in documents_response.text
    assert relations_response.status_code == 200
    assert "CARD-42" in relations_response.text
    assert "Contact Person" in relations_response.text
    assert "Rediger" in relations_response.text


def test_volunteer_relations_panel_renders_edit_state() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_courses_service] = lambda: FakeCoursesService()
    client = TestClient(app)

    response = client.get("/volunteers/12/relations/panel?edit=true")

    assert response.status_code == 200
    assert "Lagre kort og pårørende" in response.text
    assert 'hx-patch="/volunteers/12/relations"' in response.text
    assert 'name="card_number"' in response.text
    assert 'name="next_of_kin_name"' in response.text
    assert 'name="next_of_kin_phone"' in response.text
    assert "Legg til kort" in response.text
    assert "Legg til pårørende" in response.text
    assert "Avbryt redigering" in response.text


def test_volunteer_course_panel_renders_with_fake_service() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_courses_service] = lambda: FakeCoursesService()
    client = TestClient(app)

    response = client.get("/volunteers/12/course-completions/panel")

    assert response.status_code == 200
    assert "Fire safety" in response.text
    assert "Fall 2026" in response.text
    assert 'href="/courses/4"' in response.text
    assert 'hx-post="/volunteers/12/course-completions"' in response.text
    assert 'action="/volunteers/12/course-completions/11?_method=DELETE"' in response.text


def test_volunteer_relations_update_route_uses_service_for_htmx() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    service = FakeVolunteersService()
    app.dependency_overrides[get_volunteers_service] = lambda: service
    client = TestClient(app)

    response = client.post(
        "/volunteers/12/relations?_method=PATCH",
        headers={"HX-Request": "true"},
        data={
            "card_number": ["CARD-42", "CARD-99"],
            "next_of_kin_name": ["Contact Person", "Backup Contact"],
            "next_of_kin_phone": ["00000001", "00000002"],
        },
    )

    assert response.status_code == 200
    assert service.updated_relations_calls == [
        {
            "volunteer_id": 12,
            "card_numbers": ["CARD-42", "CARD-99"],
            "next_of_kin": [("Contact Person", "00000001"), ("Backup Contact", "00000002")],
        }
    ]
    assert "CARD-42" in response.text
    assert "Contact Person" in response.text


def test_volunteer_course_completion_routes_use_service_for_htmx() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    service = FakeVolunteersService()
    app.dependency_overrides[get_volunteers_service] = lambda: service
    app.dependency_overrides[get_courses_service] = lambda: FakeCoursesService()
    client = TestClient(app)

    create_response = client.post(
        "/volunteers/12/course-completions",
        headers={"HX-Request": "true"},
        data={"course_id": "5", "year": "2026", "term": "1"},
    )
    delete_response = client.post(
        "/volunteers/12/course-completions/11?_method=DELETE",
        headers={"HX-Request": "true"},
    )

    assert create_response.status_code == 200
    assert delete_response.status_code == 200
    assert service.created_course_completion_calls == [
        {
            "volunteer_id": 12,
            "course_id": 5,
            "year": 2026,
            "term": 1,
        }
    ]
    assert service.deleted_course_completion_calls == [
        {
            "volunteer_id": 12,
            "completion_id": 11,
        }
    ]


def test_volunteer_role_assignment_panel_renders_edit_state() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    response = client.get("/volunteers/12/role-assignments/panel?edit_assignment_id=5")

    assert response.status_code == 200
    assert "Rediger verv" in response.text
    assert "Avbryt redigering" in response.text
    assert 'hx-patch="/volunteers/12/role-assignments/5"' in response.text
    assert 'value="2026"' in response.text
    assert 'option value="9" selected' in response.text
    assert 'option value="2" selected' in response.text
    assert "Lagre verv" in response.text


def test_volunteer_role_assignment_update_route_uses_service_for_htmx() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    service = FakeVolunteersService()
    app.dependency_overrides[get_volunteers_service] = lambda: service
    client = TestClient(app)

    response = client.post(
        "/volunteers/12/role-assignments/5?_method=PATCH",
        headers={"HX-Request": "true"},
        data={
            "year": "2026",
            "term": "2",
            "group_id": "9",
            "role_id": "2",
            "contract_signed": "true",
        },
    )

    assert response.status_code == 200
    assert service.updated_role_assignment_calls == [
        {
            "volunteer_id": 12,
            "history_id": 5,
            "group_id": 9,
            "role_id": 2,
            "year": 2026,
            "term": 2,
            "contract_signed": True,
        }
    ]
    assert "Legg til nytt verv" in response.text


def test_volunteer_stats_page_renders_with_fake_group_service() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_groups_service] = lambda: FakeGroupsService()
    client = TestClient(app)

    response = client.get("/volunteers/stats")

    assert response.status_code == 200
    assert "Organisasjonsstatistikk" in response.text
    assert "Frivillige per semester" in response.text
    assert "Unike frivillige" in response.text
    assert "Tilbakeholdelse over tid" in response.text
    assert "Samme gruppe" in response.text
    assert "Annen gruppe" in response.text
    assert "Totalt beholdt" in response.text
    assert "Tilbakevendte" in response.text
    assert "Aktive grupper dette semesteret" in response.text


def test_volunteer_upload_endpoints_are_not_available() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    assert client.put("/volunteers/12/photo").status_code == 405
    assert client.post("/volunteers/12/documents").status_code == 404
