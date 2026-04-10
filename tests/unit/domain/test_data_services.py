from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.dialects import postgresql

from app.config import Settings
from app.domain.courses.service import (
    CoursesService,
    DuplicateCourseCompletionError,
    InvalidCourseCompletionError,
)
from app.domain.groups.service import GroupsService
from app.domain.volunteer_applications.service import (
    VolunteerAlreadyExistsError,
    VolunteerApplicationDetail,
    VolunteerApplicationSubmissionInput,
    VolunteerApplicationValidationError,
    VolunteerApplicationsService,
)
from app.domain.mobile_card.service import (
    MobileCardCurrentCardResult,
    MobileCardInvalidAccessCodeError,
    MobileCardInvalidSessionError,
    MobileCardRateLimitedError,
    MobileCardService,
    _word_of_the_day,
)
from app.domain.mobile_card.repository import (
    MobileCardRoleSnapshot,
    MobileCardSnapshot,
)
from app.domain.volunteers.service import VolunteersService
from app.domain.volunteers.repository import VolunteersRepository


class FakeVolunteersRepository:
    def __init__(self, list_rows: list[dict]) -> None:
        self.list_rows = list_rows
        self.calls: list[dict[str, int | str | None]] = []

    async def list_volunteers_page(
        self,
        *,
        limit: int,
        after_last_name: str | None = None,
        after_first_name: str | None = None,
        after_volunteer_id: int | None = None,
        only_active: bool = False,
    ):
        self.calls.append(
            {
                "method": "list_volunteers_page",
                "limit": limit,
                "after_last_name": after_last_name,
                "after_first_name": after_first_name,
                "after_volunteer_id": after_volunteer_id,
            }
        )
        return self.list_rows


class FakeVolunteerApplicationsRepository:
    def __init__(self) -> None:
        self.pending_count = 3
        self.count_calls = 0
        self.saved_registration_ids: list[int] = []
        self.saved_submission_phones: list[str | None] = []
        self.approved_registration_ids: list[int] = []
        self.deleted_registration_ids: list[int] = []
        self.created_invites: list[dict[str, object | None]] = []
        self.group_admin_email_recipients: dict[int, list[str]] = {}
        self.existing_volunteer_ids_by_email: dict[str, int] = {}
        self.application_photo_sha1: str | None = None
        self.application_photo_filetype: str | None = None
        self.application_photo_url: str | None = None

    async def create_volunteer_application_invitation(
        self,
        *,
        email: str,
        token: str,
        initial_group_id: int | None = None,
        initial_role_id: int | None = None,
    ):
        self.created_invites.append(
            {
                "email": email,
                "token": token,
                "initial_group_id": initial_group_id,
                "initial_role_id": initial_role_id,
            }
        )
        return type(
            "Invite",
            (),
            {
                "registration_id": 7,
                "token": token,
                "email": email,
                "created_at": datetime.fromisoformat("2026-03-13T12:00:00+00:00"),
                "initial_group_id": initial_group_id,
                "initial_group_name": None,
                "initial_role_id": initial_role_id,
                "initial_role_name": None,
            },
        )()

    async def list_volunteer_applications(self):
        raise NotImplementedError

    async def count_pending_volunteer_applications(self) -> int:
        self.count_calls += 1
        return self.pending_count

    async def get_volunteer_application_detail(self, registration_id: int):
        return await self.get_volunteer_application_by_token("token-123")

    async def get_volunteer_application_by_token(self, token: str):
        if token != "token-123":
            return None
        return VolunteerApplicationDetail(
            registration_id=7,
            token="token-123",
            email="registrant@example.com",
            created_at=datetime.fromisoformat("2026-03-13T12:00:00+00:00"),
            submitted=True,
            source="invite",
            status="submitted",
            pending_volunteer_id=8,
            first_name="Sample",
            last_name="Registrant",
            phone="00000000",
            birth_date=None,
            gender="K",
            address=None,
            postal_code=None,
            photo_sha1=self.application_photo_sha1,
            photo_filetype=self.application_photo_filetype,
            photo_url=self.application_photo_url,
            study_institution=None,
            background_details=None,
            initial_group_id=3,
            initial_group_name="Bar",
            initial_role_id=9,
            initial_role_name="Skiftleder",
        )

    async def save_submission(
        self,
        *,
        registration_id: int,
        email: str,
        submission: VolunteerApplicationSubmissionInput,
        photo_sha1: str | None,
        photo_filetype: str | None,
    ) -> None:
        self.saved_registration_ids.append(registration_id)
        self.saved_submission_phones.append(submission.phone)

    async def find_volunteer_id_by_email(self, email: str) -> int | None:
        return self.existing_volunteer_ids_by_email.get(email.lower())

    async def list_group_admin_email_recipients(self, group_id: int) -> list[str]:
        return list(self.group_admin_email_recipients.get(group_id, []))

    async def approve_volunteer_application(
        self,
        registration: VolunteerApplicationDetail,
        *,
        accepted_group_id: int | None,
    ) -> int:
        self.approved_registration_ids.append(registration.registration_id)
        return 12

    async def delete_volunteer_application(self, registration_id: int) -> None:
        self.deleted_registration_ids.append(registration_id)


class FakeMobileCardRepository:
    def __init__(
        self,
        volunteers_by_email: list[dict] | None = None,
        volunteer_by_email_and_code: dict | None = None,
        card_snapshot: MobileCardSnapshot | None = None,
    ) -> None:
        self.volunteers_by_email = volunteers_by_email or []
        self.volunteer_by_email_and_code = volunteer_by_email_and_code
        self.card_snapshot = card_snapshot
        self.stored_access_codes: list[tuple[int, str, datetime]] = []

    async def find_volunteers_by_email(self, email: str) -> list[dict]:
        return list(self.volunteers_by_email)

    async def store_access_code(
        self, *, volunteer_id: int, access_code: str, created_at: datetime
    ) -> None:
        self.stored_access_codes.append((volunteer_id, access_code, created_at))

    async def find_volunteer_by_email_and_code(
        self, *, email: str, access_code: str, expires_after: datetime
    ) -> dict | None:
        return self.volunteer_by_email_and_code

    async def fetch_card_snapshot(self, *, volunteer_id: int, semester_code: int):
        return self.card_snapshot


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent_emails: list[dict[str, str]] = []

    async def send_email(
        self, *, recipient_email: str, subject: str, html_body: str
    ) -> None:
        self.sent_emails.append(
            {
                "recipient_email": recipient_email,
                "subject": subject,
                "html_body": html_body,
            }
        )


def assert_applicant_email_contains(
    payload: dict[str, str],
    *,
    recipient_email: str,
    subject: str,
    invitation_url: str,
    english_phrase: str,
    norwegian_phrase: str,
) -> None:
    assert payload["recipient_email"] == recipient_email
    assert payload["subject"] == subject
    assert english_phrase in payload["html_body"]
    assert norwegian_phrase in payload["html_body"]
    assert invitation_url in payload["html_body"]
    assert "Made with" in payload["html_body"]
    assert "Med" in payload["html_body"]


class FakeMediaTokenService:
    def build_photo_media_url(self, path: str) -> str:
        return f"/media/photos/{path}?token=test"


class FakeMobileCardAprilStateService:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    async def is_enabled(self) -> bool:
        return self.enabled


def _build_mobile_card_snapshot() -> MobileCardSnapshot:
    return MobileCardSnapshot(
        volunteer_id=12,
        first_name="Ada",
        last_name="Lovelace",
        birth_date=None,
        created_at=datetime(2026, 3, 13, tzinfo=UTC),
        photo_path=None,
        pingvin_points=8,
        active_roles=[
            MobileCardRoleSnapshot(
                name="Shift lead",
                group="Bar",
                group_id=253,
                discount_level=2,
                pingvin_points=4,
                signed_contract=True,
            )
        ],
    )


@pytest.mark.asyncio
async def test_groups_service_list_uses_database_query(monkeypatch) -> None:
    service = GroupsService()
    captured = {}

    async def fake_fetch_all_mappings(stmt):
        captured["sql"] = str(stmt)
        return [
            {
                "id": 3,
                "navn": "Bar",
                "beskrivelse": "Drinks",
                "aktiv": True,
                "aktiv_til_og_med": 20262,
                "id_overgruppe": None,
                "rabatt_trinn": 1,
            }
        ]

    monkeypatch.setattr(service, "fetch_all_mappings", fake_fetch_all_mappings)

    rows = await service.list_groups(query="bar", limit=20)

    assert rows[0].group_id == 3
    assert "LIKE lower" in captured["sql"]


@pytest.mark.asyncio
async def test_group_detail_recent_members_are_scoped_to_current_semester(
    monkeypatch,
) -> None:
    service = GroupsService()
    captured = {}

    async def fake_fetch_all_mappings(stmt):
        captured["sql"] = str(stmt)
        return [
            {
                "row_type": "group",
                "group_id": 7,
                "group_name": "Bar",
                "group_description": "Drinks",
                "group_active": True,
                "group_active_until": 20262,
                "group_parent_id": None,
                "group_discount_step": 1,
                "group_created_at": "2026-03-13T12:00:00+00:00",
                "position_id": None,
                "position_name": None,
                "position_points": None,
                "position_assignment_count": None,
                "history_id": None,
                "volunteer_id": None,
                "volunteer_first_name": None,
                "volunteer_last_name": None,
                "volunteer_photo_sha1": None,
                "volunteer_photo_filetype": None,
                "member_role_name": None,
                "member_semester": None,
                "member_contract_signed": None,
            },
            {
                "row_type": "member",
                "group_id": None,
                "group_name": None,
                "group_description": None,
                "group_active": None,
                "group_active_until": None,
                "group_parent_id": None,
                "group_discount_step": None,
                "group_created_at": None,
                "position_id": None,
                "position_name": None,
                "position_points": None,
                "position_assignment_count": None,
                "history_id": 9,
                "volunteer_id": 12,
                "volunteer_first_name": "Ada",
                "volunteer_last_name": "Lovelace",
                "volunteer_photo_sha1": "abc123",
                "volunteer_photo_filetype": "jpg",
                "member_role_name": "Shift lead",
                "member_semester": 20262,
                "member_contract_signed": True,
            },
        ]

    async def fake_get_group_delete_blockers(group_id: int) -> list[str]:
        return []

    monkeypatch.setattr(service, "fetch_all_mappings", fake_fetch_all_mappings)
    monkeypatch.setattr(
        service, "_get_group_delete_blockers", fake_get_group_delete_blockers
    )
    monkeypatch.setattr("app.domain.groups.service.get_current_semester_code", lambda: 20262)

    detail = await service.get_group_detail(7)

    assert detail is not None
    assert len(detail.recent_members) == 1
    assert detail.recent_members[0].semester_code == 20262
    assert detail.recent_members[0].photo_url is not None
    assert detail.recent_members[0].photo_url.startswith("/media/photos/abc123.jpg")
    assert "historie.semester = :semester_1" in captured["sql"]


@pytest.mark.asyncio
async def test_groups_service_archive_marks_group_inactive(monkeypatch) -> None:
    service = GroupsService()
    captured = {}

    class FakeResult:
        def first(self):
            return (7,)

    class FakeSession:
        async def execute(self, stmt):
            captured["sql"] = str(
                stmt.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            )
            return FakeResult()

    async def fake_execute_in_transaction(callback):
        return await callback(FakeSession())

    monkeypatch.setattr(service, "execute_in_transaction", fake_execute_in_transaction)
    monkeypatch.setattr("app.domain.groups.service.get_current_semester_code", lambda: 20261)

    archived = await service.archive_group(7)

    assert archived is True
    assert "UPDATE public.grupper SET aktiv=false" in captured["sql"]
    assert "aktiv_til_og_med=CASE WHEN (public.grupper.aktiv_til_og_med > 20261) THEN 20261" in captured["sql"]
    assert "WHERE public.grupper.id = 7" in captured["sql"]


@pytest.mark.asyncio
async def test_courses_service_list_uses_database_query(monkeypatch) -> None:
    service = CoursesService()
    captured = {}

    async def fake_fetch_all_mappings(stmt):
        captured["sql"] = str(stmt)
        return [
            {
                "id": 9,
                "navn": "Ordensvakt",
                "beskrivelse": "Security",
                "opprettet": "2026-03-13T12:00:00+00:00",
            }
        ]

    monkeypatch.setattr(service, "fetch_all_mappings", fake_fetch_all_mappings)

    rows = await service.list_courses(query="ordens", limit=15)

    assert rows[0].course_id == 9
    assert rows[0].created_at == datetime.fromisoformat("2026-03-13T12:00:00+00:00")
    assert "LIKE lower" in captured["sql"]


@pytest.mark.asyncio
async def test_courses_service_bulk_create_inserts_all_rows(monkeypatch) -> None:
    service = CoursesService()
    captured = {}

    async def fake_course_exists(course_id: int) -> bool:
        return course_id == 4

    async def fake_list_existing_volunteer_ids(volunteer_ids: list[int]) -> set[int]:
        return set(volunteer_ids)

    async def fake_list_existing_course_completion_volunteer_ids(
        *, course_id: int, volunteer_ids: list[int], semester_code: int
    ) -> set[int]:
        captured["semester_code"] = semester_code
        return set()

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [101, 102]

    class FakeSession:
        async def execute(self, stmt, params=None):
            captured["params"] = params
            return FakeResult()

    async def fake_execute_in_transaction(callback):
        return await callback(FakeSession())

    monkeypatch.setattr(service, "_course_exists", fake_course_exists)
    monkeypatch.setattr(
        service, "_list_existing_volunteer_ids", fake_list_existing_volunteer_ids
    )
    monkeypatch.setattr(
        service,
        "_list_existing_course_completion_volunteer_ids",
        fake_list_existing_course_completion_volunteer_ids,
    )
    monkeypatch.setattr(service, "execute_in_transaction", fake_execute_in_transaction)

    created_count = await service.create_course_completions(
        course_id=4, volunteer_ids=[12, 13], year=2026, term=1
    )

    assert created_count == 2
    assert captured["semester_code"] == 20261
    assert captured["params"] == [
        {"id_personal": 12, "id_kurs": 4, "gjennomfort_dato": 20261},
        {"id_personal": 13, "id_kurs": 4, "gjennomfort_dato": 20261},
    ]


@pytest.mark.asyncio
async def test_courses_service_bulk_create_rejects_duplicate_selected_volunteers() -> (
    None
):
    service = CoursesService()

    with pytest.raises(InvalidCourseCompletionError):
        await service.create_course_completions(
            course_id=4, volunteer_ids=[12, 12], year=2026, term=1
        )


@pytest.mark.asyncio
async def test_courses_service_bulk_create_rejects_existing_same_semester_completion(
    monkeypatch,
) -> None:
    service = CoursesService()

    async def fake_course_exists(course_id: int) -> bool:
        return True

    async def fake_list_existing_volunteer_ids(volunteer_ids: list[int]) -> set[int]:
        return set(volunteer_ids)

    async def fake_list_existing_course_completion_volunteer_ids(
        *, course_id: int, volunteer_ids: list[int], semester_code: int
    ) -> set[int]:
        return {13}

    monkeypatch.setattr(service, "_course_exists", fake_course_exists)
    monkeypatch.setattr(
        service, "_list_existing_volunteer_ids", fake_list_existing_volunteer_ids
    )
    monkeypatch.setattr(
        service,
        "_list_existing_course_completion_volunteer_ids",
        fake_list_existing_course_completion_volunteer_ids,
    )

    with pytest.raises(DuplicateCourseCompletionError):
        await service.create_course_completions(
            course_id=4, volunteer_ids=[13, 14], year=2026, term=1
        )


@pytest.mark.asyncio
async def test_volunteers_service_plain_listing_uses_repository() -> None:
    repository = FakeVolunteersRepository(
        [
            {
                "id": 10016,
                "fornavn": "Martin",
                "etternavn": "Kleiven",
                "epost": "placeholder@example.test",
                "telefon": None,
                "fodselsdato": None,
                "opprettet": "2026-03-13T12:00:00+00:00",
                "sha1": None,
                "filetype": None,
                "last_semester": None,
                "pingvin_points": 0,
            }
        ]
    )
    service = VolunteersService(repository=cast(VolunteersRepository, repository))

    rows = await service.list_volunteers_page(query=None, limit=10, cursor=None)

    assert rows.items[0].full_name == "Martin Kleiven"
    assert repository.calls == [
        {
            "method": "list_volunteers_page",
            "limit": 11,
            "after_last_name": None,
            "after_first_name": None,
            "after_volunteer_id": None,
        }
    ]


@pytest.mark.asyncio
async def test_volunteers_service_search_options_are_minimal_and_sorted(
    monkeypatch,
) -> None:
    service = VolunteersService()

    async def fake_list_volunteers(query: str | None = None, limit: int = 50):
        assert query == "sample"
        assert limit == 4
        return [
            type("Volunteer", (), {"volunteer_id": 14, "full_name": "Zeta Person"})(),
            type("Volunteer", (), {"volunteer_id": 12, "full_name": "Alpha Person"})(),
        ]

    monkeypatch.setattr(service, "list_volunteers", fake_list_volunteers)

    items = await service.list_volunteer_search_options("sample", limit=2)

    assert [(item.volunteer_id, item.full_name) for item in items] == [
        (12, "Alpha Person"),
        (14, "Zeta Person"),
    ]


@pytest.mark.asyncio
async def test_volunteers_service_search_queries_use_ranked_database_path(
    monkeypatch,
) -> None:
    service = VolunteersService()

    async def fake_search(
        normalized_query: str,
        limit: int,
        cursor: str | None,
        *,
        only_active: bool = False,
    ):
        assert normalized_query == "martin kleiven"
        assert limit == 10
        assert cursor is None
        return "sentinel"

    monkeypatch.setattr(service, "_search_volunteers_page", fake_search)

    result = await service.list_volunteers_page(
        query="  Martin   Kleiven ", limit=10, cursor=None
    )

    assert result == "sentinel"


@pytest.mark.asyncio
async def test_volunteer_applications_pending_count_is_cached() -> None:
    repository = FakeVolunteerApplicationsRepository()
    service = VolunteerApplicationsService(
        settings=Settings(
            app_secret_key="test-secret",
            app_public_base_url="https://personal.kvarteret.no",
        ),
        repository=repository,
        email_sender=FakeEmailSender(),
        pending_count_cache_ttl_seconds=60,
    )

    first = await service.count_pending_volunteer_applications()
    second = await service.count_pending_volunteer_applications()

    assert first == 3
    assert second == 3
    assert repository.count_calls == 1


@pytest.mark.asyncio
async def test_volunteer_applications_submit_invalidates_pending_count_cache() -> None:
    repository = FakeVolunteerApplicationsRepository()
    repository.application_photo_sha1 = "abc123"
    repository.application_photo_filetype = "jpg"
    repository.application_photo_url = "/media/photos/abc123.jpg?token=test"
    service = VolunteerApplicationsService(
        settings=Settings(app_secret_key="test-secret"),
        repository=repository,
        email_sender=FakeEmailSender(),
        pending_count_cache_ttl_seconds=60,
    )

    await service.count_pending_volunteer_applications()
    repository.pending_count = 4
    detail = await service.submit_volunteer_application(
        "token-123",
        VolunteerApplicationSubmissionInput(
            first_name="Ada",
            last_name="Lovelace",
            phone="+4799999998",
            birth_date=None,
            gender="K",
            address=None,
            postal_code=None,
        ),
    )
    refreshed = await service.count_pending_volunteer_applications()

    assert detail.registration_id == 7
    assert refreshed == 4
    assert repository.saved_registration_ids == [7]
    assert repository.saved_submission_phones == ["+4799999998"]
    assert repository.count_calls == 2


@pytest.mark.asyncio
async def test_volunteer_applications_submit_notifies_group_admins_with_review_link() -> (
    None
):
    repository = FakeVolunteerApplicationsRepository()
    repository.group_admin_email_recipients = {
        3: ["leader@example.test", "second@example.test"]
    }
    repository.application_photo_sha1 = "abc123"
    repository.application_photo_filetype = "jpg"
    repository.application_photo_url = "/media/photos/abc123.jpg?token=test"
    email_sender = FakeEmailSender()
    service = VolunteerApplicationsService(
        settings=Settings(
            app_secret_key="test-secret",
            app_public_base_url="https://personal.kvarteret.no",
        ),
        repository=repository,
        email_sender=email_sender,
        pending_count_cache_ttl_seconds=60,
    )

    await service.submit_volunteer_application(
        "token-123",
        VolunteerApplicationSubmissionInput(
            first_name="Ada",
            last_name="Lovelace",
            phone="+4799999998",
            birth_date=None,
            gender="K",
            address="Adresse 1",
            postal_code="5000",
        ),
        base_url="https://personal.kvarteret.no",
    )

    assert email_sender.sent_emails == [
        {
            "recipient_email": "leader@example.test",
            "subject": "Ny frivilligregistrering for Bar",
            "html_body": (
                "En ny frivilligregistrering er sendt inn for Bar."
                "<br><br>"
                "Søker: Sample Registrant<br>"
                "E-post: registrant@example.com"
                "<br><br>"
                "Åpne søknaden for å gå gjennom hele profilen før du godkjenner eller avviser den:<br>"
                '<a href="https://personal.kvarteret.no/volunteer-applications/7">https://personal.kvarteret.no/volunteer-applications/7</a>'
            ),
        },
        {
            "recipient_email": "second@example.test",
            "subject": "Ny frivilligregistrering for Bar",
            "html_body": (
                "En ny frivilligregistrering er sendt inn for Bar."
                "<br><br>"
                "Søker: Sample Registrant<br>"
                "E-post: registrant@example.com"
                "<br><br>"
                "Åpne søknaden for å gå gjennom hele profilen før du godkjenner eller avviser den:<br>"
                '<a href="https://personal.kvarteret.no/volunteer-applications/7">https://personal.kvarteret.no/volunteer-applications/7</a>'
            ),
        },
    ]


@pytest.mark.asyncio
async def test_volunteer_applications_submit_normalizes_local_phone_number() -> (
    None
):
    repository = FakeVolunteerApplicationsRepository()
    repository.application_photo_sha1 = "abc123"
    repository.application_photo_filetype = "jpg"
    repository.application_photo_url = "/media/photos/abc123.jpg?token=test"
    service = VolunteerApplicationsService(
        settings=Settings(app_secret_key="test-secret"),
        repository=repository,
        email_sender=FakeEmailSender(),
        pending_count_cache_ttl_seconds=60,
    )

    await service.submit_volunteer_application(
        "token-123",
        VolunteerApplicationSubmissionInput(
            first_name="Ada",
            last_name="Lovelace",
            phone="95230903",
            birth_date=None,
            gender="K",
            address=None,
            postal_code=None,
        ),
    )

    assert repository.saved_submission_phones == ["+4795230903"]


@pytest.mark.asyncio
async def test_volunteer_applications_submit_rejects_invalid_phone_number() -> None:
    repository = FakeVolunteerApplicationsRepository()
    service = VolunteerApplicationsService(
        settings=Settings(app_secret_key="test-secret"),
        repository=repository,
        email_sender=FakeEmailSender(),
        pending_count_cache_ttl_seconds=60,
    )

    with pytest.raises(VolunteerApplicationValidationError):
        await service.submit_volunteer_application(
            "token-123",
            VolunteerApplicationSubmissionInput(
                first_name="Ada",
                last_name="Lovelace",
                phone="123",
                birth_date=None,
                gender="K",
                address=None,
                postal_code=None,
            ),
        )


@pytest.mark.asyncio
async def test_volunteer_applications_submit_requires_profile_photo_when_missing() -> (
    None
):
    repository = FakeVolunteerApplicationsRepository()
    service = VolunteerApplicationsService(
        settings=Settings(app_secret_key="test-secret"),
        repository=repository,
        email_sender=FakeEmailSender(),
        pending_count_cache_ttl_seconds=60,
    )

    with pytest.raises(
        VolunteerApplicationValidationError, match="Profilbilde er påkrevd."
    ):
        await service.submit_volunteer_application(
            "token-123",
            VolunteerApplicationSubmissionInput(
                first_name="Ada",
                last_name="Lovelace",
                phone="+4799999998",
                birth_date=None,
                gender="K",
                address=None,
                postal_code=None,
            ),
        )


@pytest.mark.asyncio
async def test_volunteer_applications_approve_invalidates_pending_count_cache() -> None:
    repository = FakeVolunteerApplicationsRepository()
    email_sender = FakeEmailSender()
    service = VolunteerApplicationsService(
        settings=Settings(
            app_secret_key="test-secret",
            app_public_base_url="https://personal.kvarteret.no",
        ),
        repository=repository,
        email_sender=email_sender,
        pending_count_cache_ttl_seconds=60,
    )

    await service.count_pending_volunteer_applications()
    repository.pending_count = 2
    volunteer_id = await service.approve_volunteer_application(7)
    refreshed = await service.count_pending_volunteer_applications()

    assert volunteer_id == 12
    assert refreshed == 2
    assert repository.approved_registration_ids == [7]
    assert repository.count_calls == 2
    assert_applicant_email_contains(
        email_sender.sent_emails[0],
        recipient_email="registrant@example.com",
        subject="Complete your Kvarteret profile / Fullfør Kvarteret-profilen din",
        invitation_url="https://personal.kvarteret.no/apply/token-123",
        english_phrase="You are now registered as a volunteer at Det Akademiske Kvarter.",
        norwegian_phrase="Du er nå registrert som frivillig i Det Akademiske Kvarter.",
    )


@pytest.mark.asyncio
async def test_volunteer_applications_delete_invalidates_pending_count_cache() -> None:
    repository = FakeVolunteerApplicationsRepository()
    service = VolunteerApplicationsService(
        settings=Settings(app_secret_key="test-secret"),
        repository=repository,
        email_sender=FakeEmailSender(),
        pending_count_cache_ttl_seconds=60,
    )

    await service.count_pending_volunteer_applications()
    repository.pending_count = 1
    await service.delete_volunteer_application(7)
    refreshed = await service.count_pending_volunteer_applications()

    assert refreshed == 1
    assert repository.deleted_registration_ids == [7]


@pytest.mark.asyncio
async def test_volunteer_applications_service_sends_email_when_creating_invitation() -> (
    None
):
    repository = FakeVolunteerApplicationsRepository()
    email_sender = FakeEmailSender()
    service = VolunteerApplicationsService(
        settings=Settings(
            app_secret_key="test-secret",
            app_public_base_url="https://personal.kvarteret.no",
        ),
        repository=repository,
        email_sender=email_sender,
        pending_count_cache_ttl_seconds=60,
    )

    invite = await service.create_volunteer_application_invitation(
        "new@example.test",
        initial_group_id=3,
        initial_role_id=9,
    )

    assert invite.email == "new@example.test"
    assert repository.created_invites[0]["email"] == "new@example.test"
    assert_applicant_email_contains(
        email_sender.sent_emails[0],
        recipient_email="new@example.test",
        subject="Complete your Kvarteret registration / Fullfør registreringen din hos Kvarteret",
        invitation_url=f"https://personal.kvarteret.no/apply/{invite.token}",
        english_phrase="You have been invited to complete your volunteer registration for Det Akademiske Kvarter.",
        norwegian_phrase="Du er invitert til å fullføre frivilligregistreringen din for Det Akademiske Kvarter.",
    )


@pytest.mark.asyncio
async def test_volunteer_applications_service_can_resend_invitation_email() -> None:
    repository = FakeVolunteerApplicationsRepository()
    email_sender = FakeEmailSender()
    service = VolunteerApplicationsService(
        settings=Settings(
            app_secret_key="test-secret",
            app_public_base_url="https://personal.kvarteret.no",
        ),
        repository=repository,
        email_sender=email_sender,
        pending_count_cache_ttl_seconds=60,
    )

    detail = await service.resend_volunteer_application_invitation(7)

    assert detail.registration_id == 7
    assert_applicant_email_contains(
        email_sender.sent_emails[0],
        recipient_email="registrant@example.com",
        subject="Complete your Kvarteret registration / Fullfør registreringen din hos Kvarteret",
        invitation_url="https://personal.kvarteret.no/apply/token-123",
        english_phrase="You have been invited to complete your volunteer registration for Det Akademiske Kvarter.",
        norwegian_phrase="Du er invitert til å fullføre frivilligregistreringen din for Det Akademiske Kvarter.",
    )


@pytest.mark.asyncio
async def test_volunteer_applications_service_can_use_explicit_base_url_without_settings_value() -> (
    None
):
    repository = FakeVolunteerApplicationsRepository()
    email_sender = FakeEmailSender()
    service = VolunteerApplicationsService(
        settings=Settings(app_secret_key="test-secret"),
        repository=repository,
        email_sender=email_sender,
        pending_count_cache_ttl_seconds=60,
    )

    invite = await service.create_volunteer_application_invitation(
        "new@example.test",
        base_url="http://localhost:8000",
    )

    assert (
        email_sender.sent_emails[0]["html_body"].find(
            f"http://localhost:8000/apply/{invite.token}"
        )
        != -1
    )


@pytest.mark.asyncio
async def test_volunteer_applications_service_rejects_duplicate_email_before_creating_invitation() -> (
    None
):
    repository = FakeVolunteerApplicationsRepository()
    repository.existing_volunteer_ids_by_email = {"existing@example.test": 42}
    email_sender = FakeEmailSender()
    service = VolunteerApplicationsService(
        settings=Settings(
            app_secret_key="test-secret",
            app_public_base_url="https://personal.kvarteret.no",
        ),
        repository=repository,
        email_sender=email_sender,
        pending_count_cache_ttl_seconds=60,
    )

    with pytest.raises(VolunteerAlreadyExistsError) as exc_info:
        await service.create_volunteer_application_invitation("existing@example.test")

    assert exc_info.value.volunteer_id == 42
    assert repository.created_invites == []
    assert email_sender.sent_emails == []


@pytest.mark.asyncio
async def test_mobile_card_service_rate_limits_repeated_invalid_session_attempts() -> (
    None
):
    service = MobileCardService(
        Settings(
            app_secret_key="test-secret",
            mobile_card_session_attempt_limit=2,
            mobile_card_session_attempt_window_seconds=600,
        ),
        repository=FakeMobileCardRepository(),  # type: ignore[arg-type]
        email_sender=FakeEmailSender(),
    )

    with pytest.raises(MobileCardInvalidAccessCodeError):
        await service.create_session(
            "person@example.com", "111111", source_key="127.0.0.1"
        )
    with pytest.raises(MobileCardInvalidAccessCodeError):
        await service.create_session(
            "person@example.com", "222222", source_key="127.0.0.1"
        )
    with pytest.raises(MobileCardRateLimitedError):
        await service.create_session(
            "person@example.com", "333333", source_key="127.0.0.1"
        )


@pytest.mark.asyncio
async def test_mobile_card_service_sends_email_when_generating_access_code() -> None:
    repository = FakeMobileCardRepository(
        volunteers_by_email=[
            {
                "id": 12,
                "fornavn": "Ada",
                "etternavn": "Lovelace",
                "internkortaccesstoken": None,
                "internkort_access_token_created_at": None,
            }
        ]
    )
    email_sender = FakeEmailSender()
    service = MobileCardService(
        Settings(app_secret_key="test-secret", mobile_card_access_code_ttl_minutes=10),
        repository=repository,  # type: ignore[arg-type]
        email_sender=email_sender,
    )

    await service.request_access_code("person@example.com")

    assert len(repository.stored_access_codes) == 1
    volunteer_id, access_code, created_at = repository.stored_access_codes[0]
    assert volunteer_id == 12
    assert created_at.tzinfo == UTC
    assert len(access_code) == 6
    assert email_sender.sent_emails[0]["recipient_email"] == "person@example.com"
    assert (
        email_sender.sent_emails[0]["subject"]
        == "Kvarteret Internkort is ready for you"
    )
    assert "Your verification code" in email_sender.sent_emails[0]["html_body"]
    assert access_code in email_sender.sent_emails[0]["html_body"]
    assert "This code expires in 10 minutes." in email_sender.sent_emails[0]["html_body"]
    assert "If you did not request this code" in email_sender.sent_emails[0]["html_body"]


@pytest.mark.asyncio
async def test_mobile_card_service_resends_recent_access_code_during_cooldown() -> None:
    repository = FakeMobileCardRepository(
        volunteers_by_email=[
            {
                "id": 12,
                "fornavn": "Ada",
                "etternavn": "Lovelace",
                "internkortaccesstoken": "654321",
                "internkort_access_token_created_at": datetime.now(UTC),
            }
        ]
    )
    email_sender = FakeEmailSender()
    service = MobileCardService(
        Settings(
            app_secret_key="test-secret", mobile_card_access_code_cooldown_seconds=60
        ),
        repository=repository,  # type: ignore[arg-type]
        email_sender=email_sender,
    )

    await service.request_access_code("person@example.com")

    assert repository.stored_access_codes == []
    assert email_sender.sent_emails[0]["html_body"].find("654321") != -1


@pytest.mark.asyncio
async def test_mobile_card_service_returns_fresh_card_without_renewal_when_token_is_new() -> (
    None
):
    repository = FakeMobileCardRepository(card_snapshot=_build_mobile_card_snapshot())
    service = MobileCardService(
        Settings(
            app_secret_key="test-secret",
            mobile_card_session_ttl_days=90,
            mobile_card_session_renewal_threshold_days=30,
        ),
        repository=repository,  # type: ignore[arg-type]
        email_sender=FakeEmailSender(),
    )

    token = service.serializer.dumps({"person_id": 12})

    result = await service.get_current_card(token)

    assert isinstance(result, MobileCardCurrentCardResult)
    assert result.card.person_id == 12
    assert result.renewed_session_token is None


@pytest.mark.asyncio
async def test_mobile_card_service_keeps_real_photo_when_april_toggle_is_disabled() -> (
    None
):
    repository = FakeMobileCardRepository(
        card_snapshot=MobileCardSnapshot(
            volunteer_id=12,
            first_name="Ada",
            last_name="Lovelace",
            birth_date=None,
            created_at=datetime(2026, 3, 13, tzinfo=UTC),
            photo_path="abc123.jpg",
            pingvin_points=8,
            active_roles=[
                MobileCardRoleSnapshot(
                    name="Skjenker",
                    group="Skjenkegruppen",
                    group_id=253,
                    discount_level=2,
                    pingvin_points=4,
                    signed_contract=True,
                )
            ],
        )
    )
    service = MobileCardService(
        Settings(app_secret_key="test-secret"),
        repository=repository,  # type: ignore[arg-type]
        email_sender=FakeEmailSender(),
        media_token_service=FakeMediaTokenService(),  # type: ignore[arg-type]
        april_state_service=FakeMobileCardAprilStateService(False),
    )

    result = await service.get_current_card(service.serializer.dumps({"person_id": 12}))

    assert result.card.photo_url == "/media/photos/abc123.jpg?token=test"


@pytest.mark.asyncio
async def test_mobile_card_service_returns_mapped_april_photo_when_toggle_is_enabled() -> (
    None
):
    repository = FakeMobileCardRepository(card_snapshot=_build_mobile_card_snapshot())
    service = MobileCardService(
        Settings(app_secret_key="test-secret"),
        repository=repository,  # type: ignore[arg-type]
        email_sender=FakeEmailSender(),
        media_token_service=FakeMediaTokenService(),  # type: ignore[arg-type]
        april_state_service=FakeMobileCardAprilStateService(True),
    )

    result = await service.get_current_card(service.serializer.dumps({"person_id": 12}))

    assert result.card.photo_url == "/static/images/april/skjenkeetaten.webp"


@pytest.mark.asyncio
async def test_mobile_card_service_uses_first_mapped_group_for_april_photo() -> None:
    repository = FakeMobileCardRepository(
        card_snapshot=MobileCardSnapshot(
            volunteer_id=12,
            first_name="Ada",
            last_name="Lovelace",
            birth_date=None,
            created_at=datetime(2026, 3, 13, tzinfo=UTC),
            photo_path="abc123.jpg",
            pingvin_points=8,
            active_roles=[
                MobileCardRoleSnapshot(
                    name="Presse",
                    group="PR-etaten",
                    group_id=270,
                    discount_level=2,
                    pingvin_points=4,
                    signed_contract=True,
                ),
                MobileCardRoleSnapshot(
                    name="Utvikler",
                    group="E-tjenesten",
                    group_id=254,
                    discount_level=2,
                    pingvin_points=4,
                    signed_contract=True,
                ),
            ],
        )
    )
    service = MobileCardService(
        Settings(app_secret_key="test-secret"),
        repository=repository,  # type: ignore[arg-type]
        email_sender=FakeEmailSender(),
        april_state_service=FakeMobileCardAprilStateService(True),
    )

    result = await service.get_current_card(service.serializer.dumps({"person_id": 12}))

    assert result.card.photo_url == "/static/images/april/pr.jpg"


@pytest.mark.asyncio
async def test_mobile_card_service_uses_default_april_photo_for_unmapped_groups() -> None:
    repository = FakeMobileCardRepository(
        card_snapshot=MobileCardSnapshot(
            volunteer_id=12,
            first_name="Ada",
            last_name="Lovelace",
            birth_date=None,
            created_at=datetime(2026, 3, 13, tzinfo=UTC),
            photo_path="abc123.jpg",
            pingvin_points=8,
            active_roles=[
                MobileCardRoleSnapshot(
                    name="Leder",
                    group="Administrasjonen",
                    group_id=263,
                    discount_level=2,
                    pingvin_points=4,
                    signed_contract=True,
                )
            ],
        )
    )
    service = MobileCardService(
        Settings(app_secret_key="test-secret"),
        repository=repository,  # type: ignore[arg-type]
        email_sender=FakeEmailSender(),
        april_state_service=FakeMobileCardAprilStateService(True),
    )

    result = await service.get_current_card(service.serializer.dumps({"person_id": 12}))

    assert result.card.photo_url == "/static/images/april/default.jpg"


@pytest.mark.asyncio
async def test_mobile_card_service_renews_session_when_token_is_near_expiry(
    monkeypatch,
) -> None:
    import itsdangerous.timed

    repository = FakeMobileCardRepository(card_snapshot=_build_mobile_card_snapshot())
    service = MobileCardService(
        Settings(
            app_secret_key="test-secret",
            mobile_card_session_ttl_days=90,
            mobile_card_session_renewal_threshold_days=30,
        ),
        repository=repository,  # type: ignore[arg-type]
        email_sender=FakeEmailSender(),
    )

    now_timestamp = itsdangerous.timed.time.time()
    sixty_five_days_in_seconds = 65 * 24 * 3600
    monkeypatch.setattr(
        itsdangerous.timed.time,
        "time",
        lambda: now_timestamp - sixty_five_days_in_seconds,
    )
    token = service.serializer.dumps({"person_id": 12})
    monkeypatch.setattr(itsdangerous.timed.time, "time", lambda: now_timestamp)

    result = await service.get_current_card(token)

    assert result.card.person_id == 12
    assert result.renewed_session_token is not None
    assert result.renewed_session_token != token


@pytest.mark.asyncio
async def test_mobile_card_service_reports_expired_token_reason(monkeypatch) -> None:
    import itsdangerous.timed

    repository = FakeMobileCardRepository(card_snapshot=_build_mobile_card_snapshot())
    service = MobileCardService(
        Settings(app_secret_key="test-secret", mobile_card_session_ttl_days=1),
        repository=repository,  # type: ignore[arg-type]
        email_sender=FakeEmailSender(),
    )

    now_timestamp = itsdangerous.timed.time.time()
    two_days_in_seconds = 2 * 24 * 3600
    monkeypatch.setattr(
        itsdangerous.timed.time,
        "time",
        lambda: now_timestamp - two_days_in_seconds,
    )
    token = service.serializer.dumps({"person_id": 12})
    monkeypatch.setattr(itsdangerous.timed.time, "time", lambda: now_timestamp)

    with pytest.raises(MobileCardInvalidSessionError) as exc_info:
        await service.get_current_card(token)

    assert exc_info.value.reason == "expired"


@pytest.mark.asyncio
async def test_mobile_card_service_reports_bad_signature_reason() -> None:
    repository = FakeMobileCardRepository(card_snapshot=_build_mobile_card_snapshot())
    service = MobileCardService(
        Settings(app_secret_key="test-secret"),
        repository=repository,  # type: ignore[arg-type]
        email_sender=FakeEmailSender(),
    )
    other_service = MobileCardService(
        Settings(app_secret_key="other-secret"),
        repository=repository,  # type: ignore[arg-type]
        email_sender=FakeEmailSender(),
    )

    token = other_service.serializer.dumps({"person_id": 12})

    with pytest.raises(MobileCardInvalidSessionError) as exc_info:
        await service.get_current_card(token)

    assert exc_info.value.reason == "bad_signature"


@pytest.mark.asyncio
async def test_mobile_card_service_reports_malformed_reason() -> None:
    repository = FakeMobileCardRepository(card_snapshot=_build_mobile_card_snapshot())
    service = MobileCardService(
        Settings(app_secret_key="test-secret"),
        repository=repository,  # type: ignore[arg-type]
        email_sender=FakeEmailSender(),
    )

    token = service.serializer.dumps({"review": False})

    with pytest.raises(MobileCardInvalidSessionError) as exc_info:
        await service.get_current_card(token)

    assert exc_info.value.reason == "malformed"


@pytest.mark.parametrize(
    ("now", "expected_word"),
    [
        (datetime(2026, 3, 2, 3, 59, 59, tzinfo=UTC), "korpingvin"),
        (datetime(2026, 3, 2, 4, 0, 0, tzinfo=UTC), "keiserpingvin"),
        (datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC), "vinpingvin"),
        (datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC), "kaffepingvin"),
    ],
)
def test_mobile_card_word_of_the_day_is_stable_for_the_effective_day(
    now: datetime, expected_word: str
) -> None:
    assert _word_of_the_day(now) == expected_word
