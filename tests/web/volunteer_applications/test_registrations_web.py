from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.auth.roles import UserRole
from app.dependencies import get_volunteer_applications_service, get_volunteers_service
from app.main import create_app
from app.domain.volunteer_applications.service import (
    PublicProspectRegistrationInput,
    RecentVolunteerRegistrationItem,
    RecentVolunteerRegistrationPage,
    VolunteerAlreadyExistsError,
    VolunteerApplicationDetail,
    VolunteerApplicationListItem,
    VolunteerApplicationInvite,
)
from app.domain.volunteers.models import AssignmentRoleOption, GroupOption
from tests.support.helpers import make_authenticated_user, override_authenticated_user


class FakeVolunteerApplicationsService:
    def __init__(self) -> None:
        self.deleted_registration_ids: list[int] = []
        self.created_invites: list[dict[str, int | str | None]] = []
        self.public_prospect_calls: list[dict[str, object | None]] = []
        self.resent_registration_ids: list[int] = []
        self.recent_registration_calls: list[dict[str, object | None]] = []
        self.submission_calls: list[dict[str, object | None]] = []
        self.volunteer_applications = [
            VolunteerApplicationListItem(
                registration_id=7,
                token="token-123",
                email="registrant@example.com",
                created_at=datetime(2026, 3, 13, tzinfo=UTC),
                submitted=True,
                source="invite",
                status="submitted",
                pending_volunteer_id=8,
                first_name="Sample",
                last_name="Registrant",
                phone="00000000",
                study_institution=None,
                background_details=None,
                initial_group_id=3,
                initial_group_name="Bar",
                initial_role_id=9,
                initial_role_name="Skiftleder",
            )
        ]
        self.recent_registration_pages = {
            None: RecentVolunteerRegistrationPage(
                items=[
                    RecentVolunteerRegistrationItem(
                        volunteer_id=12,
                        first_name="Ny",
                        last_name="Frivillig",
                        full_name="Ny Frivillig",
                        email="ny@example.com",
                        phone="+4799999999",
                        created_at=datetime(2026, 3, 15, tzinfo=UTC),
                        latest_group_name="Bar",
                        latest_role_name="Skiftleder",
                        latest_semester_code=20261,
                        latest_semester_label="Vår 2026",
                    )
                ],
                limit=20,
                cursor=None,
                next_cursor="12",
            ),
            "12": RecentVolunteerRegistrationPage(
                items=[
                    RecentVolunteerRegistrationItem(
                        volunteer_id=11,
                        first_name="Eldre",
                        last_name="Frivillig",
                        full_name="Eldre Frivillig",
                        email="eldre@example.com",
                        phone=None,
                        created_at=datetime(2026, 3, 14, tzinfo=UTC),
                        latest_group_name=None,
                        latest_role_name=None,
                        latest_semester_code=None,
                        latest_semester_label=None,
                    )
                ],
                limit=20,
                cursor="12",
                next_cursor=None,
            ),
        }

    async def create_volunteer_application_invitation(
        self,
        email: str,
        *,
        base_url: str | None = None,
        initial_group_id: int | None = None,
        initial_role_id: int | None = None,
    ) -> VolunteerApplicationInvite:
        self.created_invites.append(
            {
                "email": email,
                "base_url": base_url,
                "initial_group_id": initial_group_id,
                "initial_role_id": initial_role_id,
            }
        )
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

    async def create_public_prospect_registration(
        self,
        registration: PublicProspectRegistrationInput,
        *,
        base_url: str | None = None,
    ) -> VolunteerApplicationDetail:
        self.public_prospect_calls.append(
            {
                "full_name": registration.full_name,
                "email": registration.email,
                "phone": registration.phone,
                "study_institution": registration.study_institution,
                "background_details": registration.background_details,
                "first_choice_group_slug": registration.first_choice_group_slug,
                "second_choice_group_slug": registration.second_choice_group_slug,
                "base_url": base_url,
            }
        )
        return VolunteerApplicationDetail(
            registration_id=55,
            token="prospect-token",
            email=registration.email,
            created_at=datetime(2026, 4, 9, tzinfo=UTC),
            submitted=True,
            source="public_signup",
            status="prospect",
            pending_volunteer_id=17,
            first_name="Test",
            last_name="Person",
            phone=registration.phone,
            birth_date=None,
            gender=None,
            address=None,
            postal_code=None,
            photo_sha1=None,
            photo_filetype=None,
            photo_url=None,
            study_institution=registration.study_institution,
            background_details=registration.background_details,
            first_choice_group_name="Skjenkegruppen",
            second_choice_group_name=None,
        )

    async def list_volunteer_applications(self) -> list[VolunteerApplicationListItem]:
        return list(self.volunteer_applications)

    async def list_recent_volunteer_registrations_page(
        self,
        limit: int = 20,
        cursor: str | None = None,
    ) -> RecentVolunteerRegistrationPage:
        self.recent_registration_calls.append({"limit": limit, "cursor": cursor})
        return self.recent_registration_pages[cursor]

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
            source="invite",
            status="submitted",
            pending_volunteer_id=8,
            first_name="Sample",
            last_name="Registrant",
            phone="00000000",
            birth_date=date(1815, 12, 10),
            gender="K",
            address="Example address",
            postal_code="0000",
            photo_sha1="abc123",
            photo_filetype="jpg",
            photo_url="/media/photos/abc123.jpg?token=test",
            study_institution=None,
            background_details=None,
            initial_group_id=3,
            initial_group_name="Bar",
            initial_role_id=9,
            initial_role_name="Skiftleder",
        )

    async def submit_volunteer_application(
        self,
        token,
        submission,
        *,
        base_url: str | None = None,
        photo_filename: str | None = None,
        photo_content: bytes | None = None,
        photo_content_type: str | None = None,
    ):
        self.submission_calls.append(
            {
                "token": token,
                "base_url": base_url,
                "photo_filename": photo_filename,
                "photo_content": photo_content,
                "photo_content_type": photo_content_type,
            }
        )
        return await self.get_volunteer_application_by_token(token)

    async def approve_volunteer_application(
        self,
        registration_id: int,
        *,
        accepted_group_id: int | None = None,
        base_url: str | None = None,
    ) -> int:
        return 12

    async def resend_volunteer_application_invitation(
        self,
        registration_id: int,
        *,
        base_url: str | None = None,
    ) -> VolunteerApplicationDetail:
        self.resent_registration_ids.append(registration_id)
        detail = await self.get_volunteer_application_detail(registration_id)
        assert detail is not None
        return detail

    async def delete_volunteer_application(self, registration_id: int) -> None:
        self.deleted_registration_ids.append(registration_id)
        self.volunteer_applications = [
            application
            for application in self.volunteer_applications
            if application.registration_id != registration_id
        ]


class FakeVolunteersService:
    async def list_assignment_groups(self) -> list[GroupOption]:
        return [
            GroupOption(group_id=3, name="Bar", active=True),
            GroupOption(group_id=8, name="Ukjent", active=True),
        ]

    async def list_assignment_roles(self, group_id: int) -> list[AssignmentRoleOption]:
        if group_id != 3:
            return []
        return [AssignmentRoleOption(role_id=9, group_id=3, role_name="Skiftleder", pingvin_points=5)]


class DuplicateApprovalVolunteerApplicationsService(FakeVolunteerApplicationsService):
    async def approve_volunteer_application(
        self,
        registration_id: int,
        *,
        accepted_group_id: int | None = None,
        base_url: str | None = None,
    ) -> int:
        raise VolunteerAlreadyExistsError(10017, "sebbesgh@gmail.com")


class DuplicateInviteVolunteerApplicationsService(FakeVolunteerApplicationsService):
    async def create_volunteer_application_invitation(
        self,
        email: str,
        *,
        base_url: str | None = None,
        initial_group_id: int | None = None,
        initial_role_id: int | None = None,
    ) -> VolunteerApplicationInvite:
        raise VolunteerAlreadyExistsError(10017, email)


class InvalidPhoneVolunteerApplicationsService(FakeVolunteerApplicationsService):
    async def submit_volunteer_application(
        self,
        token,
        submission,
        *,
        base_url: str | None = None,
        photo_filename: str | None = None,
        photo_content: bytes | None = None,
        photo_content_type: str | None = None,
    ):
        from app.domain.volunteer_applications.service import VolunteerApplicationValidationError

        raise VolunteerApplicationValidationError("Skriv inn et gyldig telefonnummer.")


class NoPhotoVolunteerApplicationsService(FakeVolunteerApplicationsService):
    async def get_volunteer_application_by_token(self, token: str) -> VolunteerApplicationDetail | None:
        detail = await super().get_volunteer_application_by_token(token)
        if detail is None:
            return None
        detail.photo_sha1 = None
        detail.photo_filetype = None
        detail.photo_url = None
        return detail


class MissingPhotoVolunteerApplicationsService(FakeVolunteerApplicationsService):
    async def submit_volunteer_application(
        self,
        token,
        submission,
        *,
        base_url: str | None = None,
        photo_filename: str | None = None,
        photo_content: bytes | None = None,
        photo_content_type: str | None = None,
    ):
        from app.domain.volunteer_applications.service import VolunteerApplicationValidationError

        raise VolunteerApplicationValidationError("Profilbilde er påkrevd.")


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
    assert "Nye frivillige" in admin_response.text
    assert "Opprett invitasjon" in admin_response.text
    assert "Planlagt verv: Bar · Skiftleder" in admin_response.text
    assert "Siste nye frivillige" in admin_response.text
    assert "Ny Frivillig" in admin_response.text
    assert 'hx-get="/volunteer-applications/recent-registrations"' in admin_response.text
    assert public_response.status_code == 200
    assert "Fullfør dine detaljer" in public_response.text
    assert submitted_response.status_code == 200
    assert "Søknaden din er mottatt" in submitted_response.text
    assert "Du trenger ikke sende inn på nytt." in submitted_response.text
    assert 'enctype="multipart/form-data"' in public_response.text
    assert 'name="profile_photo"' in public_response.text
    assert 'data-photo-input' in public_response.text
    assert 'data-photo-preview' in public_response.text
    assert 'src="/media/photos/abc123.jpg?token=test"' in public_response.text
    assert "URL.createObjectURL(file)" in public_response.text
    assert 'pattern="\\+[1-9][0-9]{7,14}"' not in public_response.text
    assert 'placeholder="91234567"' in public_response.text
    assert 'name="profile_photo"' in public_response.text


def test_volunteer_application_form_requires_photo_when_none_exists() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteer_applications_service] = lambda: NoPhotoVolunteerApplicationsService()
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    response = client.get("/apply/token-123")

    assert response.status_code == 200
    assert 'name="profile_photo"' in response.text
    assert 'name="profile_photo"' in response.text and "required" in response.text


def test_volunteer_application_detail_page_renders_full_preview() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_volunteer_applications_service] = lambda: FakeVolunteerApplicationsService()
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    response = client.get("/volunteer-applications/7")

    assert response.status_code == 200
    assert "Søkerprofil" in response.text
    assert "Registrering" in response.text
    assert "registrant@example.com" in response.text
    assert "Promoter til frivillig" in response.text
    assert "Prøvedugnad" in response.text
    assert "Lenke" not in response.text


def test_recent_registrations_fragment_renders_next_page() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    volunteer_applications_service = FakeVolunteerApplicationsService()
    app.dependency_overrides[get_volunteer_applications_service] = lambda: volunteer_applications_service
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    response = client.get("/volunteer-applications/recent-registrations", params={"cursor": "12"})

    assert response.status_code == 200
    assert "Eldre Frivillig" in response.text
    assert "Ingen startgruppe registrert" in response.text
    assert volunteer_applications_service.recent_registration_calls == [{"limit": 20, "cursor": "12"}]


def test_group_admin_can_open_new_volunteer_page_with_all_groups() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user(UserRole.GROUP_ADMIN))
    app.dependency_overrides[get_volunteer_applications_service] = lambda: FakeVolunteerApplicationsService()
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    response = client.get("/volunteer-applications")

    assert response.status_code == 200
    assert "Opprett invitasjon" in response.text
    assert "registrant@example.com" in response.text
    assert 'option value="3"' in response.text
    assert 'option value="8"' in response.text


def test_group_admin_can_create_invite() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user(UserRole.GROUP_ADMIN))
    volunteer_applications_service = FakeVolunteerApplicationsService()
    app.dependency_overrides[get_volunteer_applications_service] = lambda: volunteer_applications_service
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    response = client.post(
        "/volunteer-applications",
        data={"email": "new@example.test", "group_id": "3", "role_id": "9"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/volunteer-applications"
    assert volunteer_applications_service.created_invites == [
        {
            "email": "new@example.test",
            "base_url": "http://testserver",
            "initial_group_id": 3,
            "initial_role_id": 9,
        }
    ]


def test_group_admin_create_invite_redirects_to_existing_volunteer_on_duplicate_email() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user(UserRole.GROUP_ADMIN))
    app.dependency_overrides[get_volunteer_applications_service] = lambda: DuplicateInviteVolunteerApplicationsService()
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    response = client.post(
        "/volunteer-applications",
        data={"email": "existing@example.test", "group_id": "3", "role_id": "9"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/volunteers/10017"


def test_group_admin_can_create_invite_without_group() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user(UserRole.GROUP_ADMIN))
    volunteer_applications_service = FakeVolunteerApplicationsService()
    app.dependency_overrides[get_volunteer_applications_service] = lambda: volunteer_applications_service
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    response = client.post(
        "/volunteer-applications",
        data={"email": "new@example.test"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert volunteer_applications_service.created_invites == [
        {
            "email": "new@example.test",
            "base_url": "http://testserver",
            "initial_group_id": None,
            "initial_role_id": None,
        }
    ]


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
            "phone": "+4791234567",
            "birth_date": "1815-12-10",
            "gender": "K",
            "address": "Example address",
            "postal_code": "0000",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/apply/token-123/submitted"


def test_volunteer_application_submit_accepts_profile_photo_upload() -> None:
    app = create_app()
    override_authenticated_user(app, None)
    volunteer_applications_service = FakeVolunteerApplicationsService()
    app.dependency_overrides[get_volunteer_applications_service] = lambda: volunteer_applications_service
    client = TestClient(app)

    response = client.post(
        "/apply/token-123",
        data={
            "first_name": "Sample",
            "last_name": "Registrant",
            "phone": "+4791234567",
            "birth_date": "1815-12-10",
            "gender": "K",
            "address": "Example address",
            "postal_code": "0000",
        },
        files={"profile_photo": ("avatar.png", b"fake-image", "image/png")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert volunteer_applications_service.submission_calls == [
        {
            "token": "token-123",
            "base_url": "http://testserver",
            "photo_filename": "avatar.png",
            "photo_content": b"fake-image",
            "photo_content_type": "image/png",
        }
    ]


def test_volunteer_application_submit_rejects_profile_photo_over_40mb() -> None:
    app = create_app()
    override_authenticated_user(app, None)
    volunteer_applications_service = FakeVolunteerApplicationsService()
    app.dependency_overrides[get_volunteer_applications_service] = lambda: volunteer_applications_service
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
        files={"profile_photo": ("avatar.png", b"x" * (40 * 1024 * 1024 + 1), "image/png")},
        follow_redirects=False,
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Photos must be 40 MB or smaller."}
    assert volunteer_applications_service.submission_calls == []


def test_volunteer_application_submit_rejects_invalid_phone() -> None:
    app = create_app()
    override_authenticated_user(app, None)
    app.dependency_overrides[get_volunteer_applications_service] = lambda: InvalidPhoneVolunteerApplicationsService()
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

    assert response.status_code == 400
    assert "gyldig telefonnummer" in response.text


def test_volunteer_application_submit_rejects_missing_profile_photo() -> None:
    app = create_app()
    override_authenticated_user(app, None)
    app.dependency_overrides[get_volunteer_applications_service] = lambda: MissingPhotoVolunteerApplicationsService()
    client = TestClient(app)

    response = client.post(
        "/apply/token-123",
        data={
            "first_name": "Sample",
            "last_name": "Registrant",
            "phone": "+4791234567",
            "birth_date": "1815-12-10",
            "gender": "K",
            "address": "Example address",
            "postal_code": "0000",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Profilbilde er påkrevd." in response.text


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


def test_volunteer_application_delete_redirects_from_boosted_detail_page() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    volunteer_applications_service = FakeVolunteerApplicationsService()
    app.dependency_overrides[get_volunteer_applications_service] = lambda: volunteer_applications_service
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    response = client.delete(
        "/volunteer-applications/7",
        headers={"HX-Request": "true", "HX-Boosted": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/volunteer-applications"
    assert volunteer_applications_service.deleted_registration_ids == [7]


def test_volunteer_application_resend_redirects_and_calls_service() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    volunteer_applications_service = FakeVolunteerApplicationsService()
    volunteer_applications_service.volunteer_applications = [
        VolunteerApplicationListItem(
            registration_id=7,
            token="token-123",
            email="registrant@example.com",
            created_at=datetime(2026, 3, 13, tzinfo=UTC),
            submitted=False,
            source="invite",
            status="invited",
            pending_volunteer_id=None,
            first_name=None,
            last_name=None,
            phone=None,
            study_institution=None,
            background_details=None,
            initial_group_id=3,
            initial_group_name="Bar",
            initial_role_id=9,
            initial_role_name="Skiftleder",
        )
    ]
    app.dependency_overrides[get_volunteer_applications_service] = lambda: volunteer_applications_service
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    page_response = client.get("/volunteer-applications")
    resend_response = client.post("/volunteer-applications/7/resend", follow_redirects=False)

    assert page_response.status_code == 200
    assert "Send e-post på nytt" in page_response.text
    assert resend_response.status_code == 303
    assert resend_response.headers["location"] == "/volunteer-applications"
    assert volunteer_applications_service.resent_registration_ids == [7]


def test_group_admin_can_manage_any_registration() -> None:
    class OtherGroupVolunteerApplicationsService(FakeVolunteerApplicationsService):
        async def get_volunteer_application_detail(self, registration_id: int) -> VolunteerApplicationDetail | None:
            if registration_id != 8:
                return None
            return VolunteerApplicationDetail(
                registration_id=8,
                token="token-456",
                email="other@example.com",
                created_at=datetime(2026, 3, 14, tzinfo=UTC),
                submitted=True,
                source="public_signup",
                status="prospect",
                pending_volunteer_id=9,
                first_name="Other",
                last_name="Person",
                phone="11111111",
                birth_date=None,
                gender=None,
                address=None,
                postal_code=None,
                photo_sha1=None,
                photo_filetype=None,
                photo_url=None,
                study_institution="UiB",
                background_details=None,
                initial_group_id=8,
                initial_group_name="Ukjent",
                initial_role_id=None,
                initial_role_name=None,
            )

    app = create_app()
    override_authenticated_user(app, make_authenticated_user(UserRole.GROUP_ADMIN))
    volunteer_applications_service = OtherGroupVolunteerApplicationsService()
    volunteer_applications_service.volunteer_applications = [
        VolunteerApplicationListItem(
            registration_id=8,
            token="token-456",
            email="other@example.com",
            created_at=datetime(2026, 3, 14, tzinfo=UTC),
            submitted=True,
            source="public_signup",
            status="prospect",
            pending_volunteer_id=9,
            first_name="Other",
            last_name="Person",
            phone="11111111",
            study_institution="UiB",
            background_details=None,
            initial_group_id=8,
            initial_group_name="Ukjent",
            initial_role_id=None,
            initial_role_name=None,
        )
    ]
    app.dependency_overrides[get_volunteer_applications_service] = lambda: volunteer_applications_service
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    client = TestClient(app)

    list_response = client.get("/volunteer-applications")
    delete_response = client.delete("/volunteer-applications/8", headers={"HX-Request": "true"})

    assert list_response.status_code == 200
    assert "other@example.com" in list_response.text
    assert delete_response.status_code == 200
    assert volunteer_applications_service.deleted_registration_ids == [8]


def test_public_prospect_api_accepts_missing_second_choice() -> None:
    app = create_app()
    volunteer_applications_service = FakeVolunteerApplicationsService()
    app.dependency_overrides[get_volunteer_applications_service] = lambda: volunteer_applications_service
    client = TestClient(app)

    response = client.post(
        "/api/v1/volunteer-prospects",
        json={
            "full_name": "Test Person",
            "email": "prospect@example.com",
            "phone": "12345678",
            "study_institution": "UiB",
            "background_details": None,
            "first_choice_group_slug": "skjenkegruppen",
        },
    )

    assert response.status_code == 201
    assert response.json() == {"registrationId": 55}
    assert volunteer_applications_service.public_prospect_calls == [
        {
            "full_name": "Test Person",
            "email": "prospect@example.com",
            "phone": "12345678",
            "study_institution": "UiB",
            "background_details": None,
            "first_choice_group_slug": "skjenkegruppen",
            "second_choice_group_slug": None,
            "base_url": "http://testserver",
        }
    ]
