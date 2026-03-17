from __future__ import annotations

from datetime import datetime

import pytest

from app.services.courses import CoursesService
from app.services.groups import GroupsService
from app.services.volunteer_applications import (
    VolunteerApplicationDetail,
    VolunteerApplicationSubmissionInput,
    VolunteerApplicationsService,
)
from app.services.volunteers import VolunteersService


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
        self.approved_registration_ids: list[int] = []
        self.deleted_registration_ids: list[int] = []

    async def create_volunteer_application_invitation(self, *, email: str, token: str):
        raise NotImplementedError

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
            pending_volunteer_id=8,
            first_name="Sample",
            last_name="Registrant",
            phone="00000000",
            birth_date=None,
            gender="K",
            address=None,
            postal_code=None,
            employment_status=1,
            photo_sha1=None,
            photo_filetype=None,
            photo_url=None,
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

    async def find_volunteer_id_by_email(self, email: str) -> int | None:
        return None

    async def approve_volunteer_application(self, registration: VolunteerApplicationDetail) -> int:
        self.approved_registration_ids.append(registration.registration_id)
        return 12

    async def delete_volunteer_application(self, registration_id: int) -> None:
        self.deleted_registration_ids.append(registration_id)


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
async def test_group_detail_recent_members_are_scoped_to_current_semester(monkeypatch) -> None:
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
                "member_role_name": "Shift lead",
                "member_semester": 20262,
                "member_contract_signed": True,
            },
        ]

    async def fake_get_group_delete_blockers(group_id: int) -> list[str]:
        return []

    monkeypatch.setattr(service, "fetch_all_mappings", fake_fetch_all_mappings)
    monkeypatch.setattr(service, "_get_group_delete_blockers", fake_get_group_delete_blockers)
    monkeypatch.setattr("app.services.groups.get_current_semester_code", lambda: 20262)

    detail = await service.get_group_detail(7)

    assert detail is not None
    assert len(detail.recent_members) == 1
    assert detail.recent_members[0].semester_code == 20262
    assert "historie.semester = :semester_1" in captured["sql"]


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
    service = VolunteersService(repository=repository)

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
async def test_volunteers_service_search_queries_use_ranked_database_path(monkeypatch) -> None:
    service = VolunteersService()

    async def fake_search(normalized_query: str, limit: int, cursor: str | None):
        assert normalized_query == "martin kleiven"
        assert limit == 10
        assert cursor is None
        return "sentinel"

    monkeypatch.setattr(service, "_search_volunteers_page", fake_search)

    result = await service.list_volunteers_page(query="  Martin   Kleiven ", limit=10, cursor=None)

    assert result == "sentinel"


@pytest.mark.asyncio
async def test_volunteer_applications_pending_count_is_cached() -> None:
    repository = FakeVolunteerApplicationsRepository()
    service = VolunteerApplicationsService(repository=repository, pending_count_cache_ttl_seconds=60)

    first = await service.count_pending_volunteer_applications()
    second = await service.count_pending_volunteer_applications()

    assert first == 3
    assert second == 3
    assert repository.count_calls == 1


@pytest.mark.asyncio
async def test_volunteer_applications_submit_invalidates_pending_count_cache() -> None:
    repository = FakeVolunteerApplicationsRepository()
    service = VolunteerApplicationsService(repository=repository, pending_count_cache_ttl_seconds=60)

    await service.count_pending_volunteer_applications()
    repository.pending_count = 4
    detail = await service.submit_volunteer_application(
        "token-123",
        VolunteerApplicationSubmissionInput(
            first_name="Ada",
            last_name="Lovelace",
            phone=None,
            birth_date=None,
            gender="K",
            address=None,
            postal_code=None,
            employment_status=1,
        ),
    )
    refreshed = await service.count_pending_volunteer_applications()

    assert detail.registration_id == 7
    assert refreshed == 4
    assert repository.saved_registration_ids == [7]
    assert repository.count_calls == 2


@pytest.mark.asyncio
async def test_volunteer_applications_approve_invalidates_pending_count_cache() -> None:
    repository = FakeVolunteerApplicationsRepository()
    service = VolunteerApplicationsService(repository=repository, pending_count_cache_ttl_seconds=60)

    await service.count_pending_volunteer_applications()
    repository.pending_count = 2
    volunteer_id = await service.approve_volunteer_application(7)
    refreshed = await service.count_pending_volunteer_applications()

    assert volunteer_id == 12
    assert refreshed == 2
    assert repository.approved_registration_ids == [7]
    assert repository.count_calls == 2


@pytest.mark.asyncio
async def test_volunteer_applications_delete_invalidates_pending_count_cache() -> None:
    repository = FakeVolunteerApplicationsRepository()
    service = VolunteerApplicationsService(repository=repository, pending_count_cache_ttl_seconds=60)

    await service.count_pending_volunteer_applications()
    repository.pending_count = 1
    await service.delete_volunteer_application(7)
    refreshed = await service.count_pending_volunteer_applications()

    assert refreshed == 1
    assert repository.deleted_registration_ids == [7]
    assert repository.count_calls == 2
