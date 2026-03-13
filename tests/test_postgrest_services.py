from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from app.config import Settings
from app.postgrest import PostgrestClient
from app.services.courses import CoursesService
from app.services.groups import GroupsService
from app.services.people import PeopleService


@pytest.mark.asyncio
async def test_postgrest_client_select_rows_uses_rest_contract() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json=[{"id": 1, "navn": "Bar"}])

    client = httpx.AsyncClient(
        base_url="https://example.supabase.co/rest/v1",
        transport=httpx.MockTransport(handler),
    )
    postgrest = PostgrestClient(
        Settings(supabase_url="https://example.supabase.co", supabase_secret_key="secret"),
        client=client,
    )

    rows = await postgrest.select_rows(
        "grupper",
        select="id,navn",
        filters={"or": "(navn.ilike.*bar*)"},
        order="navn.asc,id.asc",
        limit=10,
    )

    assert rows == [{"id": 1, "navn": "Bar"}]
    assert captured["path"] == "/rest/v1/grupper"
    assert captured["query"]["select"] == "id,navn"
    assert captured["query"]["or"] == "(navn.ilike.*bar*)"
    assert captured["query"]["order"] == "navn.asc,id.asc"
    assert captured["query"]["limit"] == "10"
    await client.aclose()


class FakePostgrestClient:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    async def select_rows(self, table: str, *, select: str, filters=None, order=None, limit=None, offset=None):
        self.calls.append(
            {
                "table": table,
                "select": select,
                "filters": filters,
                "order": order,
                "limit": limit,
                "offset": offset,
            }
        )
        return self.rows


@pytest.mark.asyncio
async def test_groups_service_list_uses_postgrest_client() -> None:
    client = FakePostgrestClient(
        [
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
    )
    service = GroupsService(postgrest_client=client)

    rows = await service.list_groups(query="bar", limit=20)

    assert rows[0].group_id == 3
    assert client.calls[0]["table"] == "grupper"
    assert client.calls[0]["limit"] == 20
    assert "navn.ilike.*bar*" in client.calls[0]["filters"]["or"]


@pytest.mark.asyncio
async def test_courses_service_list_uses_postgrest_client() -> None:
    client = FakePostgrestClient(
        [
            {
                "id": 9,
                "navn": "Ordensvakt",
                "beskrivelse": "Security",
                "opprettet": "2026-03-13T12:00:00+00:00",
            }
        ]
    )
    service = CoursesService(postgrest_client=client)

    rows = await service.list_courses(query="ordens", limit=15)

    assert rows[0].course_id == 9
    assert rows[0].created_at == datetime.fromisoformat("2026-03-13T12:00:00+00:00")
    assert client.calls[0]["table"] == "kurs"
    assert client.calls[0]["limit"] == 15
    assert "navn.ilike.*ordens*" in client.calls[0]["filters"]["or"]


@pytest.mark.asyncio
async def test_people_service_plain_listing_uses_postgrest_client() -> None:
    client = FakePostgrestClient(
        [
            {
                "id": 10016,
                "fornavn": "Martin",
                "etternavn": "Kleiven",
                "epost": "placeholder@example.test",
                "telefon": None,
                "fodselsdato": None,
                "opprettet": "2026-03-13T12:00:00+00:00",
                "personal_bilde": None,
            }
        ]
    )
    service = PeopleService(postgrest_client=client)

    rows = await service.list_people_page(query=None, limit=10, offset=0)

    assert rows.items[0].full_name == "Martin Kleiven"
    assert client.calls[0]["table"] == "personal"
    assert client.calls[0]["filters"] is None


@pytest.mark.asyncio
async def test_people_service_search_queries_use_ranked_database_path(monkeypatch) -> None:
    service = PeopleService(postgrest_client=None)

    async def fake_search(normalized_query: str, limit: int, offset: int):
        assert normalized_query == "martin kleiven"
        assert limit == 10
        assert offset == 0
        return "sentinel"

    monkeypatch.setattr(service, "_search_people_page", fake_search)

    result = await service.list_people_page(query="  Martin   Kleiven ", limit=10, offset=0)

    assert result == "sentinel"
