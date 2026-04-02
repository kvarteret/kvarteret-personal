from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.dependencies import get_mobile_card_service
from app.main import create_app
from app.domain.mobile_card.service import MobileCardPersonNotFoundError
from app.domain.mobile_card.service import (
    MobileCardCurrentCardResult,
    MobileCardInvalidAccessCodeError,
    MobileCardResponse,
    MobileCardRole,
    MobileCardRateLimitedError,
    MobileCardSession,
)


class FakeMobileCardService:
    async def request_access_code(
        self, email: str, *, source_key: str | None = None
    ) -> None:
        if email == "missing@example.com":
            raise MobileCardPersonNotFoundError(
                "Email not found in the personnel database."
            )
        if email == "rate-limited@example.com":
            raise MobileCardRateLimitedError(
                "Too many access-code requests. Try again later."
            )

    async def create_session(
        self, email: str, access_code: str, *, source_key: str | None = None
    ) -> MobileCardSession:
        if email == "missing@example.com":
            raise MobileCardPersonNotFoundError(
                "Email not found in the personnel database."
            )
        if email == "rate-limited@example.com":
            raise MobileCardRateLimitedError(
                "Too many access-code attempts. Try again later."
            )
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

    async def get_current_card(self, session_token: str) -> MobileCardCurrentCardResult:
        if session_token != "token-123":
            if session_token == "renew-me":
                return MobileCardCurrentCardResult(
                    card=(
                        await self.create_session("person.one@example.com", "123456")
                    ).card,
                    renewed_session_token="token-456",
                )
            raise MobileCardInvalidAccessCodeError("Unknown session token.")
        return MobileCardCurrentCardResult(
            card=(await self.create_session("person.one@example.com", "123456")).card,
        )


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
    assert "x-mobile-card-session-token" not in me_response.headers


def test_new_mobile_card_me_returns_renewed_token_header_when_available() -> None:
    client = _make_client()

    response = client.get(
        "/api/v1/mobile-card/me", headers={"Authorization": "Bearer renew-me"}
    )

    assert response.status_code == 200
    assert response.headers["x-mobile-card-session-token"] == "token-456"


def test_new_mobile_card_me_requires_known_bearer_token() -> None:
    client = _make_client()

    response = client.get(
        "/api/v1/mobile-card/me", headers={"Authorization": "Bearer invalid"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unknown session token."


def test_mobile_card_access_code_request_does_not_expose_whether_email_exists() -> None:
    client = _make_client()

    response = client.post(
        "/api/v1/mobile-card/access-codes",
        json={"email": "missing@example.com"},
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}


def test_mobile_card_session_returns_generic_invalid_credentials() -> None:
    client = _make_client()

    response = client.post(
        "/api/v1/mobile-card/sessions",
        json={"email": "missing@example.com", "access_code": "123456"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or access code."}


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

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_legacy_mobile_card_session_uses_generic_invalid_credentials() -> None:
    client = _make_client()

    response = client.post(
        "/api/DigitalInternkort/GetInternkortInformation",
        json={"email": "missing@example.com", "accessToken": "123456"},
    )

    assert response.status_code == 401
    assert response.text == "Invalid email or access code."


def test_mobile_card_access_code_request_returns_429_when_rate_limited() -> None:
    client = _make_client()

    response = client.post(
        "/api/v1/mobile-card/access-codes",
        json={"email": "rate-limited@example.com"},
    )

    assert response.status_code == 429
    assert response.json() == {
        "detail": "Too many access-code requests. Try again later."
    }


def test_mobile_card_client_logout_event_accepts_valid_payload() -> None:
    client = _make_client()

    response = client.post(
        "/api/v1/mobile-card/client-events/session-logout",
        json={
            "app_version": "2026.2.0",
            "auth_error_code": "INVALID_AUTH",
            "auth_error_message": "Session expired. Please sign in again.",
            "auth_error_status": 401,
            "cached_user_id": 12,
            "event_name": "session_invalidated",
            "execution_environment": "standalone",
            "had_cached_user": True,
            "had_login_marker": True,
            "had_stored_credentials": True,
            "occurred_at": "2026-03-28T10:15:00.000Z",
            "platform": "ios",
            "runtime_version": "2026.2.0",
            "update_channel": "production",
            "update_id": "update-123",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}


def test_mobile_card_client_logout_event_rejects_invalid_payload() -> None:
    client = _make_client()

    response = client.post(
        "/api/v1/mobile-card/client-events/session-logout",
        json={
            "event_name": "not-valid",
            "had_cached_user": True,
            "had_login_marker": True,
            "had_stored_credentials": True,
            "occurred_at": "2026-03-28T10:15:00.000Z",
            "platform": "ios",
        },
    )

    assert response.status_code == 422
