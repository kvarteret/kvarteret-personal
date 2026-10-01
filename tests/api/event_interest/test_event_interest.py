import hashlib
import hmac
import json
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.event_interest import router
from app.config import Settings
from app.db.rate_limit import InMemoryRateLimiter
from app.dependencies import get_event_interest_service, get_rate_limiter, get_settings

SECRET = "event-interest-test-secret-0123456789"


class Service:
    def __init__(self):
        self.calls = []

    async def read(self, event_id, source_hash):
        self.calls.append((event_id, source_hash))
        return {"taps": 0, "score": 0}

    async def save(self, event_id, source_hash, taps):
        self.calls.append((event_id, source_hash, taps))
        return {"taps": taps, "score": 1}


def client_and_service():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/event-interest")
    service = Service()
    app.dependency_overrides[get_event_interest_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: Settings(
        event_interest_secret=SECRET
    )
    limiter = InMemoryRateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    return TestClient(app), service


def signed(payload, path="/api/v1/event-interest/response", timestamp=None):
    body = json.dumps(payload).encode()
    timestamp = timestamp or str(int(time.time()))
    nonce = str(uuid4())
    canonical = "\n".join(
        (
            "event-interest-v1",
            timestamp,
            nonce,
            "POST",
            path,
            hashlib.sha256(body).hexdigest(),
        )
    )
    return body, {
        "Content-Type": "application/json",
        "X-Kvarteret-Timestamp": timestamp,
        "X-Kvarteret-Nonce": nonce,
        "X-Kvarteret-Signature": "v1="
        + hmac.new(SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest(),
    }


def test_valid_and_replayed_signed_write():
    client, service = client_and_service()
    body, headers = signed(
        {"event_id": "sanity-event", "source_hash": "a" * 64, "taps": 12}
    )
    response = client.post(
        "/api/v1/event-interest/response", content=body, headers=headers
    )
    assert response.status_code == 200
    assert response.json() == {"taps": 12, "score": 1}
    assert response.headers["Cache-Control"] == "private, no-store"
    assert (
        client.post(
            "/api/v1/event-interest/response", content=body, headers=headers
        ).status_code
        == 429
    )
    assert len(service.calls) == 1


def test_invalid_stale_and_tampered_auth():
    client, service = client_and_service()
    payload = {"event_id": "event", "source_hash": "a" * 64, "taps": 4}
    assert (
        client.post("/api/v1/event-interest/response", json=payload).status_code == 401
    )
    body, headers = signed(payload, timestamp=str(int(time.time()) - 301))
    assert (
        client.post(
            "/api/v1/event-interest/response", content=body, headers=headers
        ).status_code
        == 401
    )
    body, headers = signed(payload)
    assert (
        client.post(
            "/api/v1/event-interest/response",
            content=body.replace(b'"taps": 4', b'"taps": 8'),
            headers=headers,
        ).status_code
        == 401
    )
    assert not service.calls


def test_strict_bounds_and_private_read():
    client, service = client_and_service()
    for taps in [13, -1, 1.5, True, "4"]:
        body, headers = signed(
            {"event_id": "event", "source_hash": "a" * 64, "taps": taps}
        )
        assert (
            client.post(
                "/api/v1/event-interest/response", content=body, headers=headers
            ).status_code
            == 422
        )
    path = "/api/v1/event-interest/read"
    body, headers = signed({"event_id": "event"}, path)
    assert client.post(path, content=body, headers=headers).json() == {
        "taps": 0,
        "score": 0,
    }
    assert service.calls == [("event", None)]
