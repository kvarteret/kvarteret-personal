from __future__ import annotations

from fastapi.testclient import TestClient

from app.dependencies import get_rate_limiter, require_authenticated_user
from app.db.rate_limit import InMemoryRateLimiter
from app.main import create_app
from tests.support.helpers import make_authenticated_user


def _make_client() -> tuple[TestClient, InMemoryRateLimiter]:
    app = create_app()
    limiter = InMemoryRateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    app.dependency_overrides[require_authenticated_user] = lambda: make_authenticated_user()
    return TestClient(app), limiter


def test_client_error_report_accepts_valid_payload() -> None:
    client, _ = _make_client()

    response = client.post(
        "/api/v1/telemetry/client-errors",
        json={
            "error_type": "uncaught",
            "error_text": "Something broke",
            "error_source": "/courses/4",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_client_error_report_rejects_unknown_fields() -> None:
    client, _ = _make_client()

    response = client.post(
        "/api/v1/telemetry/client-errors",
        json={"error_text": "x", "hax": "payload"},
    )

    assert response.status_code == 422


def test_client_error_report_requires_authentication() -> None:
    app = create_app()
    app.dependency_overrides[get_rate_limiter] = lambda: InMemoryRateLimiter()
    # require_authenticated_user is left unresolved -> no user -> 401.
    client = TestClient(app)

    response = client.post(
        "/api/v1/telemetry/client-errors",
        json={"error_text": "x"},
    )

    assert response.status_code == 401


def test_client_error_report_rate_limits_runaway_reports() -> None:
    app = create_app()
    limiter = InMemoryRateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    app.dependency_overrides[require_authenticated_user] = lambda: make_authenticated_user()
    client = TestClient(app)

    # The endpoint ceiling is 60 reports per 60-second window per user.
    for _ in range(60):
        response = client.post(
            "/api/v1/telemetry/client-errors",
            json={"error_text": "boom"},
        )
        assert response.status_code == 200

    response = client.post(
        "/api/v1/telemetry/client-errors",
        json={"error_text": "boom"},
    )
    assert response.status_code == 429


def test_third_failed_submission_creates_exception_with_safe_diagnostics(caplog) -> None:
    import logging
    from app.observability import JsonLogFormatter
    client, _ = _make_client()
    logging.getLogger().addHandler(caplog.handler)
    with caplog.at_level(logging.ERROR):
        response = client.post("/api/v1/telemetry/client-errors", json={
            "error_type": "RepeatedFormSubmissionFailure", "attempt_count": 3,
            "form_id": "/volunteers/:id", "validation_fields": "body.role_id",
            "validation_codes": "int_parsing", "status_code": 422,
        })
    assert response.status_code == 200
    record = next(r for r in caplog.records if r.getMessage() == "form.submission.repeated_failure")
    assert record.exc_info[0].__name__ == "RepeatedFormSubmissionFailure"
    assert 'body.role_id' in JsonLogFormatter().format(record)
