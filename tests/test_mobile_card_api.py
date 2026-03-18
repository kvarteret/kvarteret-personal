from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from app.dependencies import get_mobile_card_service
from app.main import create_app
from app.services.mobile_card import (
    MobileCardInvalidAccessCodeError,
    MobileCardResponse,
    MobileCardRole,
    MobileCardSession,
)


class FakeMobileCardService:
    async def request_access_code(self, email: str) -> None:
        if email == "missing@example.com":
            from app.services.mobile_card import MobileCardPersonNotFoundError

            raise MobileCardPersonNotFoundError("Email not found in the personnel database.")

    async def create_session(self, email: str, access_code: str) -> MobileCardSession:
        if access_code != "123456":
            raise MobileCardInvalidAccessCodeError("Invalid access code.")
        card = MobileCardResponse(
            person_id=12,
            first_name="Sample",
            last_name="Person",
            birth_date=date(1815, 12, 10),
            created_at=datetime(2026, 3, 13, tzinfo=UTC),
            valid_until=datetime(2026, 3, 20, tzinfo=UTC),
            photo_url="/media/photos/abc.jpg?token=test",
            pingvin_points=8,
            active_roles=[
                MobileCardRole(
                    name="Shift lead",
                    group="Bar",
                    discount_level=2,
                    pingvin_points=4,
                    signed_contract=True,
                )
            ],
            word_of_the_day="pingvin",
        )
        return MobileCardSession(session_token="token-123", card=card)

    async def get_current_card(self, session_token: str) -> MobileCardResponse:
        if session_token != "token-123":
            raise MobileCardInvalidAccessCodeError("Unknown session token.")
        return (
            await self.create_session("person.one@example.com", "123456")
        ).card


def _make_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_mobile_card_service] = lambda: FakeMobileCardService()
    return TestClient(app)


def test_new_mobile_card_session_flow_returns_english_contract() -> None:
    client = _make_client()

    access_code_response = client.post(
        "/api/v1/mobile-card/access-codes",
        json={"email": "person.one@example.com"},
    )
    session_response = client.post(
        "/api/v1/mobile-card/sessions",
        json={"email": "person.one@example.com", "access_code": "123456"},
    )

    assert access_code_response.status_code == 202
    assert access_code_response.json() == {"status": "accepted"}

    payload = session_response.json()
    assert session_response.status_code == 200
    assert payload["session_token"] == "token-123"
    assert payload["card"]["first_name"] == "Sample"
    assert payload["card"]["active_roles"][0]["name"] == "Shift lead"
    assert payload["card"]["active_roles"][0]["pingvin_points"] == 4

    me_response = client.get(
        "/api/v1/mobile-card/me",
        headers={"Authorization": f"Bearer {payload['session_token']}"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["person_id"] == 12


def test_new_mobile_card_me_requires_known_bearer_token() -> None:
    client = _make_client()

    response = client.get("/api/v1/mobile-card/me", headers={"Authorization": "Bearer invalid"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Unknown session token."


def test_legacy_mobile_card_adapter_returns_legacy_contract() -> None:
    client = _make_client()

    response = client.post(
        "/api/DigitalInternkort/GetInternkortInformation",
        json={"email": "person.one@example.com", "accessToken": "123456"},
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["fornavn"] == "Sample"
    assert payload["aktiveVerv"][0]["navn"] == "Shift lead"
    assert payload["aktiveVerv"][0]["pingvinPoeng"] == 4
    assert "pingvinPoengSum" in payload


def test_legacy_mobile_card_errors_return_plain_text_for_mobile_app() -> None:
    client = _make_client()

    response = client.post(
        "/api/DigitalInternkort/RequestAccessTokenOnEmail",
        json={"email": "missing@example.com"},
    )

    assert response.status_code == 404
    assert response.text == "Email not found in the personnel database."
