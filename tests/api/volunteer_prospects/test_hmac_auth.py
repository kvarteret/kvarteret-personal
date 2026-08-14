from __future__ import annotations

import json
import time
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.request_auth import (
    VOLUNTEER_PROSPECT_PATH,
    build_volunteer_prospect_signature,
)
from app.api.v1.volunteer_prospects import router
from app.config import Settings
from app.db.rate_limit import InMemoryRateLimiter
from app.dependencies import (
    get_rate_limiter,
    get_settings,
    get_volunteer_applications_service,
)

HMAC_SECRET = "test-shared-secret-0123456789abcdef"
PREVIOUS_HMAC_SECRET = "previous-shared-secret-0123456789abc"
FIXED_TIMESTAMP = "1760000000"
FIXED_NONCE = "123e4567-e89b-42d3-a456-426614174000"
FIXED_BODY = (
    b'{"full_name":"Kari Nordmann","email":"kari@example.com"}'
)
FIXED_SIGNATURE = (
    "v1=3cfde76a38294df695c172ea02132ea8902860cd6709894e1d93779ccbec6b53"
)

VALID_PAYLOAD = {
    "full_name": "Kari Nordmann",
    "email": "kari@example.com",
    "phone": "+4740612345",
    "study_institution": "UiB",
    "first_choice_group_slug": "kraftetaten",
}


class FakeVolunteerApplicationsService:
    def __init__(self) -> None:
        self.calls = 0

    async def create_public_prospect_registration(self, registration, *, base_url):
        self.calls += 1
        return SimpleNamespace(registration_id=42)


def _build_app(
    *,
    secret: str | None = HMAC_SECRET,
    previous_secret: str | None = None,
) -> tuple[FastAPI, FakeVolunteerApplicationsService]:
    app = FastAPI()
    app.include_router(router, prefix=VOLUNTEER_PROSPECT_PATH)
    service = FakeVolunteerApplicationsService()
    limiter = InMemoryRateLimiter()
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="test",
        volunteer_prospect_hmac_secret=secret,
        volunteer_prospect_hmac_previous_secret=previous_secret,
    )
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_volunteer_applications_service] = lambda: service
    return app, service


def _encoded_payload(payload: dict | None = None) -> bytes:
    return json.dumps(payload or VALID_PAYLOAD, separators=(",", ":")).encode()


def _signed_headers(
    body: bytes,
    *,
    secret: str = HMAC_SECRET,
    timestamp: str | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    resolved_timestamp = timestamp or str(int(time.time()))
    resolved_nonce = nonce or str(uuid4())
    return {
        "Content-Type": "application/json",
        "X-Kvarteret-Timestamp": resolved_timestamp,
        "X-Kvarteret-Nonce": resolved_nonce,
        "X-Kvarteret-Signature": build_volunteer_prospect_signature(
            secret,
            timestamp=resolved_timestamp,
            nonce=resolved_nonce,
            method="POST",
            path=VOLUNTEER_PROSPECT_PATH,
            body=body,
        ),
    }


def test_hmac_signature_matches_shared_cross_repository_vector() -> None:
    assert (
        build_volunteer_prospect_signature(
            HMAC_SECRET,
            timestamp=FIXED_TIMESTAMP,
            nonce=FIXED_NONCE,
            method="POST",
            path=VOLUNTEER_PROSPECT_PATH,
            body=FIXED_BODY,
        )
        == FIXED_SIGNATURE
    )


def test_signed_prospect_request_is_accepted() -> None:
    app, service = _build_app()
    body = _encoded_payload()

    response = TestClient(app).post(
        VOLUNTEER_PROSPECT_PATH,
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 201
    assert response.json() == {"registrationId": 42}
    assert service.calls == 1


def test_unsigned_prospect_request_is_rejected() -> None:
    app, service = _build_app()

    response = TestClient(app).post(
        VOLUNTEER_PROSPECT_PATH,
        json=VALID_PAYLOAD,
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Request authentication failed."}
    assert response.headers["WWW-Authenticate"] == "HMAC"
    assert service.calls == 0


def test_unsigned_malformed_body_never_reaches_prospect_service() -> None:
    app, service = _build_app()

    response = TestClient(app).post(
        VOLUNTEER_PROSPECT_PATH,
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert service.calls == 0


def test_signature_does_not_authorize_an_altered_body() -> None:
    app, service = _build_app()
    signed_body = _encoded_payload()
    altered_body = _encoded_payload({**VALID_PAYLOAD, "phone": "+4799999999"})

    response = TestClient(app).post(
        VOLUNTEER_PROSPECT_PATH,
        content=altered_body,
        headers=_signed_headers(signed_body),
    )

    assert response.status_code == 401
    assert service.calls == 0


def test_stale_signature_is_rejected() -> None:
    app, service = _build_app()
    body = _encoded_payload()
    stale_timestamp = str(int(time.time()) - 301)

    response = TestClient(app).post(
        VOLUNTEER_PROSPECT_PATH,
        content=body,
        headers=_signed_headers(body, timestamp=stale_timestamp),
    )

    assert response.status_code == 401
    assert service.calls == 0


def test_replayed_nonce_is_rejected() -> None:
    app, service = _build_app()
    client = TestClient(app)
    body = _encoded_payload()
    headers = _signed_headers(body)

    first_response = client.post(
        VOLUNTEER_PROSPECT_PATH,
        content=body,
        headers=headers,
    )
    replayed_response = client.post(
        VOLUNTEER_PROSPECT_PATH,
        content=body,
        headers=headers,
    )

    assert first_response.status_code == 201
    assert replayed_response.status_code == 401
    assert service.calls == 1


def test_previous_secret_is_accepted_during_rotation() -> None:
    app, service = _build_app(previous_secret=PREVIOUS_HMAC_SECRET)
    body = _encoded_payload()

    response = TestClient(app).post(
        VOLUNTEER_PROSPECT_PATH,
        content=body,
        headers=_signed_headers(body, secret=PREVIOUS_HMAC_SECRET),
    )

    assert response.status_code == 201
    assert service.calls == 1


def test_missing_hmac_configuration_fails_closed() -> None:
    app, service = _build_app(secret=None)
    body = _encoded_payload()

    response = TestClient(app).post(
        VOLUNTEER_PROSPECT_PATH,
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable."}
    assert service.calls == 0
