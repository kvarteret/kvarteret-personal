import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.dependencies import get_rate_limiter
from app.db.rate_limit import InMemoryRateLimiter
from app.observability import JsonLogFormatter
from app.telemetry import DomainLogFilter


def payload(event="session_invalidated"):
    return dict(
        event_name=event,
        event_id="test-event",
        operation_id="test-operation",
        attempt_id="test-event:1",
        attempt_no=1,
        source="client",
        occurred_at="2026-10-06T13:00:00Z",
        platform="ios",
        app_version="2026.2.0",
        auth_error_code="INVALID_AUTH",
        auth_error_status=401,
        had_cached_user=True,
        had_login_marker=True,
        had_stored_credentials=True,
    )


def client():
    app = create_app()
    limiter = InMemoryRateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    return TestClient(app)


@pytest.mark.parametrize(
    "event,severity",
    [
        ("session_invalidated", logging.WARNING),
        ("credentials_missing_after_login", logging.WARNING),
        ("logout_succeeded", logging.INFO),
        ("logout_failed", logging.WARNING),
        ("cache_fallback_started", logging.DEBUG),
        ("cache_fallback_recovered", logging.DEBUG),
    ],
)
def test_signed_out_diagnostics_preserve_safe_context(caplog, event, severity):
    c = client()
    logging.getLogger().addHandler(caplog.handler)
    with caplog.at_level(logging.DEBUG):
        response = c.post(
            "/api/v1/mobile-card/client-events/diagnostics",
            json=payload(event),
            headers={"X-Session-ID": "a" * 32, "X-Request-ID": "test-request"},
        )
    assert response.status_code == 202
    record = next(
        r for r in caplog.records if getattr(r, "event", "").startswith("mobile_card.")
    )
    data = json.loads(JsonLogFormatter().format(record))
    assert record.levelno == severity
    assert DomainLogFilter().filter(record) == (severity >= logging.INFO)
    assert data["session_id"] == "a" * 32
    assert data["request_id"] == "test-request"
    assert data["event_id"] == "test-event"
    if event == "session_invalidated":
        assert data["failure_stage"] == "reauthorization"
        assert data["auth_error_status"] == 401
        assert data["had_stored_credentials"] is True


@pytest.mark.parametrize(
    "extra",
    [
        {"auth_error_message": "secret"},
        {"token": "secret"},
        {"event_name": "visit"},
        {"attempt_no": 0},
    ],
)
def test_invalid_diagnostics_are_rejected(extra):
    assert (
        client()
        .post(
            "/api/v1/mobile-card/client-events/diagnostics", json={**payload(), **extra}
        )
        .status_code
        == 422
    )


def test_rate_limit_bounds_public_ingestion():
    c = client()
    for _ in range(60):
        assert (
            c.post(
                "/api/v1/mobile-card/client-events/diagnostics", json=payload()
            ).status_code
            == 202
        )
    assert (
        c.post(
            "/api/v1/mobile-card/client-events/diagnostics", json=payload()
        ).status_code
        == 429
    )
