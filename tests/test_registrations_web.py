from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.dependencies import get_volunteer_applications_service
from app.main import create_app
from app.services.volunteer_applications import VolunteerApplicationDetail, VolunteerApplicationListItem, VolunteerApplicationInvite
from tests.helpers import make_authenticated_user, override_authenticated_user


class FakeVolunteerApplicationsService:
    async def create_volunteer_application_invitation(self, email: str) -> VolunteerApplicationInvite:
        return VolunteerApplicationInvite(7, "token-123", email, datetime(2026, 3, 13, tzinfo=UTC))

    async def list_volunteer_applications(self) -> list[VolunteerApplicationListItem]:
        return [
            VolunteerApplicationListItem(
                registration_id=7,
                token="token-123",
                email="registrant@example.com",
                created_at=datetime(2026, 3, 13, tzinfo=UTC),
                submitted=True,
                first_name="Sample",
                last_name="Registrant",
                phone="00000000",
            )
        ]

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
        )

    async def submit_volunteer_application(self, token, submission):
        return await self.get_volunteer_application_by_token(token)

    async def approve_volunteer_application(self, registration_id: int) -> int:
        return 12

    async def delete_volunteer_application(self, registration_id: int) -> None:
        return None


def test_volunteer_application_pages_render() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteer_applications_service] = lambda: FakeVolunteerApplicationsService()
    client = TestClient(app)

    admin_response = client.get("/volunteer-applications")
    public_response = client.get("/apply/token-123")

    assert admin_response.status_code == 200
    assert "Frivilligsøknader" in admin_response.text
    assert "Opprett invitasjon" in admin_response.text
    assert public_response.status_code == 200
    assert "Fullfør dine detaljer" in public_response.text
    assert 'enctype="multipart/form-data"' in public_response.text
    assert 'name="profile_photo"' in public_response.text
