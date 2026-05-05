from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.dependencies import get_events_service, get_mobile_card_service
from app.domain.events import EventsService
from app.domain.mobile_card.service import MobileCardInvalidAccessCodeError
from app.main import create_app


NOW = datetime.now(UTC)


class FakeEventsRepository:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []
        self.list_calls: list[dict] = []

    async def list_events(
        self, *, include_internal: bool, now: datetime, fetch_limit: int
    ):
        self.list_calls.append(
            {
                "include_internal": include_internal,
                "fetch_limit": fetch_limit,
            }
        )
        return [
            row
            for row in self.rows
            if row["status"] == "published"
            and row["event_end"] >= now
            and (include_internal or not row["is_internal"])
        ][:fetch_limit]

    async def get_event(self, event_id: UUID):
        return next((row for row in self.rows if row["id"] == event_id), None)

    async def list_event_types(self):
        return [
            {
                "id": uuid4(),
                "slug": "konsert",
                "name": "Konsert",
                "description": None,
                "taxonomy_group": "Musikk",
                "sort_order": 10,
                "is_active": True,
            },
            {
                "id": uuid4(),
                "slug": "debatt",
                "name": "Debatt",
                "description": None,
                "taxonomy_group": "Faglig",
                "sort_order": 20,
                "is_active": True,
            },
        ]

    async def list_organizer_groups(self):
        return [
            {
                "id": uuid4(),
                "slug": "samfunnet",
                "name": "Samfunnet",
                "sort_order": 10,
                "is_active": True,
                "default_event_type_id": None,
            }
        ]

    async def list_rooms(self):
        return [
            {
                "id": uuid4(),
                "slug": "teglverket",
                "name": "Teglverket",
                "sort_order": 10,
                "is_active": True,
            }
        ]


class FakeMobileCardService:
    async def get_current_card(self, session_token: str):
        if session_token != "valid-mobile-session":
            raise MobileCardInvalidAccessCodeError("Unknown session token.")
        return object()


def _make_client(repository: FakeEventsRepository) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_events_service] = lambda: EventsService(repository)  # type: ignore[arg-type]
    app.dependency_overrides[get_mobile_card_service] = lambda: FakeMobileCardService()
    return TestClient(app)


def _event_row(
    *,
    event_id: UUID | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    is_internal: bool = False,
    is_featured: bool = False,
    translations: dict | None = None,
):
    event_type_id = uuid4()
    room_id = uuid4()
    return {
        "id": event_id or uuid4(),
        "slug": "sample-event",
        "status": "published",
        "event_start": starts_at or (NOW + timedelta(hours=2)),
        "event_end": ends_at or (NOW + timedelta(hours=4)),
        "created_at": NOW - timedelta(days=1),
        "updated_at": NOW - timedelta(hours=1),
        "ticket_url": "https://tickets.example.test",
        "facebook_url": None,
        "image_url": "https://images.example.test/event.webp",
        "price": "100",
        "event_type_id": event_type_id,
        "room_id": room_id,
        "room_text": None,
        "is_internal": is_internal,
        "is_featured": is_featured,
        "recurring_interval_days": None,
        "translations": translations
        or {
            "no": {
                "available": True,
                "title": "Norsk tittel",
                "description": "Norsk tekst",
                "image_caption": "Norsk bildetekst",
            },
            "en": {
                "available": True,
                "title": "English title",
                "description": "English text",
                "image_caption": "English caption",
            },
        },
        "event_type__id": event_type_id,
        "event_type__slug": "konsert",
        "event_type__name": "Konsert",
        "event_type__description": None,
        "event_type__taxonomy_group": "Musikk",
        "event_type__sort_order": 10,
        "event_type__is_active": True,
        "room__id": room_id,
        "room__slug": "teglverket",
        "room__name": "Teglverket",
        "room__sort_order": 10,
        "room__is_active": True,
        "organizer_groups": [
            {
                "id": uuid4(),
                "slug": "samfunnet",
                "name": "Samfunnet",
                "sort_order": 10,
                "is_active": True,
                "default_event_type_id": None,
            }
        ],
    }


def test_public_event_list_uses_public_non_ended_query_and_api_field_names() -> None:
    repository = FakeEventsRepository(
        [
            _event_row(is_internal=False),
            _event_row(is_internal=True),
            _event_row(is_internal=False, ends_at=NOW - timedelta(minutes=1)),
        ]
    )
    client = _make_client(repository)

    response = client.get(
        "/api/v1/events", headers={"Accept-Language": "nb-NO, en;q=0.7"}
    )

    assert response.status_code == 200
    assert (
        response.headers["cache-control"]
        == "public, max-age=30, s-maxage=300, stale-while-revalidate=600"
    )
    assert response.headers["content-language"] == "no"
    assert response.headers["vary"] == "Accept-Language, Authorization"
    payload = response.json()
    assert len(payload["events"]) == 1
    event = payload["events"][0]
    assert event["title"] == "Norsk tittel"
    assert event["starts_at"]
    assert event["ends_at"]
    assert event["image_url"] == "https://images.example.test/event.webp"
    assert "event_start" not in event
    assert "event_end" not in event
    assert "image" not in event
    assert repository.list_calls[0]["include_internal"] is False


def test_valid_mobile_session_can_include_internal_events() -> None:
    repository = FakeEventsRepository(
        [_event_row(is_internal=False), _event_row(is_internal=True)]
    )
    client = _make_client(repository)

    response = client.get(
        "/api/v1/events?include_internal=true",
        headers={"Authorization": "Bearer valid-mobile-session"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert len(response.json()["events"]) == 2
    assert repository.list_calls[0]["include_internal"] is True


def test_invalid_event_bearer_returns_unauthorized() -> None:
    client = _make_client(FakeEventsRepository([_event_row()]))

    response = client.get(
        "/api/v1/events",
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid bearer token."


def test_include_internal_requires_mobile_session() -> None:
    client = _make_client(FakeEventsRepository([_event_row(is_internal=True)]))

    response = client.get("/api/v1/events?include_internal=true")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token."


def test_internal_event_detail_without_auth_is_hidden() -> None:
    event_id = uuid4()
    client = _make_client(
        FakeEventsRepository([_event_row(event_id=event_id, is_internal=True)])
    )

    response = client.get(f"/api/v1/events/{event_id}")

    assert response.status_code == 404


def test_accept_language_selects_english_and_falls_back_to_available_translation() -> (
    None
):
    event_id = uuid4()
    client = _make_client(
        FakeEventsRepository(
            [
                _event_row(
                    event_id=event_id,
                    translations={
                        "no": {
                            "available": True,
                            "title": "Bare norsk",
                            "description": None,
                            "image_caption": None,
                        },
                        "en": None,
                    },
                )
            ]
        )
    )

    response = client.get(
        f"/api/v1/events/{event_id}", headers={"Accept-Language": "en-US"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert response.headers["content-language"] == "no"
    assert payload["language"] == "no"
    assert payload["title"] == "Bare norsk"
    assert payload["translations"]["no"]["title"] == "Bare norsk"


def test_event_taxonomy_groups_active_types_with_metadata() -> None:
    client = _make_client(FakeEventsRepository())

    response = client.get("/api/v1/events/taxonomy")

    assert response.status_code == 200
    assert (
        response.headers["cache-control"]
        == "public, max-age=30, s-maxage=300, stale-while-revalidate=600"
    )
    payload = response.json()
    assert [group["name"] for group in payload["event_type_groups"]] == [
        "Musikk",
        "Faglig",
    ]
    assert (
        payload["event_type_groups"][0]["event_types"][0]["taxonomy_group"] == "Musikk"
    )
    assert payload["organizer_groups"][0]["slug"] == "samfunnet"
    assert payload["rooms"][0]["slug"] == "teglverket"
