from __future__ import annotations

from datetime import datetime

import pytest

from app.services.courses import CoursesService
from app.services.groups import GroupsService
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
