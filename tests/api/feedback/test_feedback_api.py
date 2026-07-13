from __future__ import annotations

from fastapi.testclient import TestClient

from app.dependencies import get_feedback_service
from app.domain.feedback.service import FeedbackRateLimitedError
from app.main import create_app


class CapturingFeedbackService:
    def __init__(self, *, rate_limited: bool = False) -> None:
        self.rate_limited = rate_limited
        self.calls: list[dict[str, object]] = []

    async def submit_feedback(self, **kwargs: object) -> None:
        self.calls.append(kwargs)
        if self.rate_limited:
            raise FeedbackRateLimitedError(
                "Too many feedback submissions. Try again later."
            )


def _make_client(service: CapturingFeedbackService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_feedback_service] = lambda: service
    return TestClient(app)


def test_feedback_api_passes_client_ip_to_service() -> None:
    service = CapturingFeedbackService()
    client = _make_client(service)

    response = client.post(
        "/api/v1/feedback/",
        json={"message": "Hei", "source": "internbevis-rn"},
        headers={"X-Forwarded-For": "203.0.113.10"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert service.calls[0]["source_key"] == "203.0.113.10"


def test_feedback_api_returns_429_when_rate_limited() -> None:
    client = _make_client(CapturingFeedbackService(rate_limited=True))

    response = client.post(
        "/api/v1/feedback/",
        json={"message": "Hei", "source": "internbevis-rn"},
    )

    assert response.status_code == 429
    assert response.json() == {
        "detail": "Too many feedback submissions. Try again later."
    }


def test_feedback_api_rejects_unverified_identity_fields() -> None:
    service = CapturingFeedbackService()
    client = _make_client(service)

    response = client.post(
        "/api/v1/feedback/",
        json={
            "message": "Hei",
            "source": "internbevis-rn",
            "user_id": 123,
            "user_full_name": "Spoofed Member",
        },
    )

    assert response.status_code == 422
    assert service.calls == []
