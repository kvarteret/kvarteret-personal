from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.dependencies import get_volunteer_applications_service, get_volunteers_service
from app.main import create_app
from app.services.volunteer_applications import (
    VolunteerAlreadyExistsError,
    VolunteerApplicationDetail,
    VolunteerApplicationListItem,
    VolunteerApplicationInvite,
)
from app.services.volunteer_models import AssignmentRoleOption, GroupOption
from tests.helpers import make_authenticated_user, override_authenticated_user


class FakeVolunteerApplicationsService:
    def __init__(self) -> None:
        self.deleted_registration_ids: list[int] = []
        self.volunteer_applications = [
            VolunteerApplicationListItem(
                registration_id=7,
                token="token-123",
                email="registrant@example.com",
                created_at=datetime(2026, 3, 13, tzinfo=UTC),
                submitted=True,
                first_name="Sample",
                last_name="Registrant",
                phone="00000000",
                initial_group_id=3,
                initial_group_name="Bar",
                initial_role_id=9,
                initial_role_name="Skiftleder",
            )
        ]

    async def create_volunteer_application_invitation(
        self,
        email: str,
        *,
        initial_group_id: int | None = None,
        initial_role_id: int | None = None,
    ) -> VolunteerApplicationInvite:
        return VolunteerApplicationInvite(
            7,
            "token-123",
            email,
            datetime(2026, 3, 13, tzinfo=UTC),
            initial_group_id=initial_group_id,
            initial_group_name="Bar" if initial_group_id else None,
            initial_role_id=initial_role_id,
            initial_role_name="Skiftleder" if initial_role_id else None,
        )

    async def list_volunteer_applications(self) -> list[VolunteerApplicationListItem]:
        return list(self.volunteer_applications)

    async def count_pending_volunteer_applications(self) -> int:
        return 1

    async def get_volunteer_application_detail(self, registration_id: int) -> VolunteerApplicationDetail | None:
        return await self.get_volunteer_application_by_token("token-123")

    async def get_volunteer_application_by_token(self, token: str) -> VolunteerApplicationDetail | None:
        if token != "token-123":
            return None
        return VolunteerApplicationDetail(
            registration_id=7,
            token="token-123",
            email="registrant@example.com",
            created_at=datetime(2026, 3, 13, tzinfo=UTC),
            submitted=True,
            pending_volunteer_id=8,
            first_name="Sample",
            last_name="Registrant",
            phone="00000000",
            birth_date=date(1815, 12, 10),
            gender="K",
            address="Example address",
            postal_code="0000",
            employment_status=1,
            photo_sha1="abc123",
            photo_filetype="jpg",
            photo_url="/media/photos/abc123.jpg?token=test",
            initial_group_id=3,
            initial_group_name="Bar",
            initial_role_id=9,
            initial_role_name="Skiftleder",
        )

    async def submit_volunteer_application(self, token, submission):
        return await self.get_volunteer_application_by_token(token)

    async def approve_volunteer_application(self, registration_id: int) -> int:
        return 12

    async def delete_volunteer_application(self, registration_id: int) -> None:
        self.deleted_registration_ids.append(registration_id)
        self.volunteer_applications = [
            application
            for application in self.volunteer_applications
            if application.registration_id != registration_id
        ]


class FakeVolunteersService:
    async def list_assignment_groups(self) -> list[GroupOption]:
        return [GroupOption(group_id=3, name="Bar", active=True)]

    async def list_assignment_roles(self, group_id: int) -> list[AssignmentRoleOption]:
        if group_id != 3:
            return []
        return [AssignmentRoleOption(role_id=9, group_id=3, role_name="Skiftleder", pingvin_points=5)]


class DuplicateApprovalVolunteerApplicationsService(FakeVolunteerApplicationsService):
    async def approve_volunteer_application(self, registration_id: int) -> int:
        raise VolunteerAlreadyExistsError(10017, "sebbesgh@gmail.com")


def test_volunteer_application_pages_render() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteer_applications_service] = lambda: FakeVolunteerApplicationsService()
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    admin_response = client.get("/volunteer-applications")
    public_response = client.get("/apply/token-123")
    submitted_response = client.get("/apply/token-123/submitted")

    assert admin_response.status_code == 200
    assert "Frivilligsøknader" in admin_response.text
    assert "Opprett invitasjon" in admin_response.text
    assert "Planlagt verv: Bar · Skiftleder" in admin_response.text
    assert public_response.status_code == 200
    assert "Fullfør dine detaljer" in public_response.text
    assert submitted_response.status_code == 200
    assert "Status OK" in submitted_response.text
    assert "Venter på godkjenning" in submitted_response.text
    assert 'enctype="multipart/form-data"' not in public_response.text
    assert 'name="profile_photo"' not in public_response.text


def test_duplicate_volunteer_approval_redirects_to_existing_profile() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteer_applications_service] = lambda: DuplicateApprovalVolunteerApplicationsService()
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    response = client.post("/volunteer-applications/7/approval", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/volunteers/10017?duplicate_application_id=7"


def test_volunteer_application_submit_redirects_to_pending_status_page() -> None:
    app = create_app()
    override_authenticated_user(app, None)
    app.dependency_overrides[get_volunteer_applications_service] = lambda: FakeVolunteerApplicationsService()
    client = TestClient(app)

    response = client.post(
        "/apply/token-123",
        data={
            "first_name": "Sample",
            "last_name": "Registrant",
            "phone": "00000000",
            "birth_date": "1815-12-10",
            "gender": "K",
            "address": "Example address",
            "postal_code": "0000",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/apply/token-123/submitted"


def test_volunteer_application_delete_rerenders_list_for_htmx() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    volunteer_applications_service = FakeVolunteerApplicationsService()
    app.dependency_overrides[get_volunteer_applications_service] = lambda: volunteer_applications_service
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    response = client.delete("/volunteer-applications/7", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert volunteer_applications_service.deleted_registration_ids == [7]
    assert "registrant@example.com" not in response.text
    assert "Ingen åpne frivilligsøknader." in response.text
