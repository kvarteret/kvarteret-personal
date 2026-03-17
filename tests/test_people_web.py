from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from io import BytesIO

from app.dependencies import get_groups_service, get_volunteers_service
from app.main import create_app
from app.services.groups import GroupBreakdownItem, GroupMemberCount, OrgSemesterDetailed, SemesterRetentionStats
from app.services.volunteer_models import (
    CardItem,
    DocumentItem,
    GroupOption,
    RoleAssignmentItem,
    NextOfKinItem,
    VolunteerDetail,
    VolunteerListItem,
    VolunteerListPage,
    VolunteerRelations,
    AssignmentRoleOption,
)
from tests.helpers import make_authenticated_user, override_authenticated_user


class FakeVolunteersService:
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
                    photo_url=None,
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
            employment_status=1,
            photo_url=None,
        )

    async def list_role_assignments(self, volunteer_id: int, limit: int = 12) -> list[RoleAssignmentItem]:
        return [
            RoleAssignmentItem(
                history_id=5,
                group_id=9,
                group_name="Bar",
                role_id=2,
                role_name="Shift lead",
                semester_code=20262,
                semester_label="Fall 2026",
                contract_signed=True,
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
                retained_to_next=8,
                churned=3,
            ),
            SemesterRetentionStats(
                semester_code=20262,
                semester_label="Fall 2026",
                total_members=14,
                retained_from_prev=8,
                new_members=6,
                retained_to_next=0,
                churned=14,
            ),
        ]


def test_volunteer_pages_render_with_fake_service() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_groups_service] = lambda: FakeGroupsService()
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
    assert "Laster filer" in detail_response.text
    assert "Laster kort og pårørende" in detail_response.text
    assert "name=\"gender\"" in detail_response.text
    assert f'action="/volunteers/12/photo?_method=PUT"' in detail_response.text
    assert 'hx-trigger="intersect once"' in detail_response.text


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
    assert "Slett verv" in history_response.text
    assert "kontrakt" in history_response.text
    assert 'href="/groups/9"' in history_response.text
    assert documents_response.status_code == 200
    assert "certificate.pdf" in documents_response.text
    assert "window.confirm('Slette denne filen?')" in documents_response.text
    assert relations_response.status_code == 200
    assert "CARD-42" in relations_response.text
    assert "Contact Person" in relations_response.text


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
    assert "Tilbakevendte" in response.text
    assert "Aktive grupper dette semesteret" in response.text


def test_volunteer_upload_endpoints_reject_files_over_30mb() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    oversized = BytesIO(b"x" * (30 * 1024 * 1024 + 1))

    photo_response = client.put(
        "/volunteers/12/photo",
        files={"file": ("photo.jpg", oversized, "image/jpeg")},
    )

    document_response = client.post(
        "/volunteers/12/documents",
        data={"group_id": ""},
        files={"file": ("doc.pdf", BytesIO(b"x" * (30 * 1024 * 1024 + 1)), "application/pdf")},
    )

    assert photo_response.status_code == 400
    assert photo_response.json() == {"detail": "File exceeds 30 MB limit."}
    assert document_response.status_code == 400
    assert document_response.json() == {"detail": "File exceeds 30 MB limit."}
