from __future__ import annotations

from fastapi.testclient import TestClient

from app.dependencies import get_feedback_service
from app.domain.feedback.service import FeedbackDeliveryError, FeedbackRateLimitedError
from app.main import create_app
from tests.support.helpers import make_authenticated_user, override_authenticated_user


class FakeFeedbackService:
    def __init__(self) -> None:
        self.calls: list[dict[str, str | None]] = []

    async def submit_feedback(
        self,
        *,
        category: str,
        name: str | None,
        email: str | None,
        message: str,
        page: str,
        source_key: str | None,
    ) -> None:
        self.calls.append(
            {
                "category": category,
                "name": name,
                "email": email,
                "message": message,
                "page": page,
                "source_key": source_key,
            }
        )


class FailingFeedbackService:
    async def submit_feedback(self, **_kwargs) -> None:
        raise FeedbackDeliveryError("LINEAR_API_KEY is not configured.")


class RateLimitedFeedbackService:
    async def submit_feedback(self, **_kwargs) -> None:
        raise FeedbackRateLimitedError("Too many feedback submissions. Try again later.")


def test_feedback_panel_renders() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    client = TestClient(app)

    response = client.get("/feedback/panel?page=/volunteers")

    assert response.status_code == 200
    assert 'role="dialog"' in response.text
    assert "Ris / Ros / Forslag" in response.text
    assert "Sender som" in response.text
    assert "System User" in response.text


def test_feedback_submit_posts_via_htmx() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    feedback_service = FakeFeedbackService()
    app.dependency_overrides[get_feedback_service] = lambda: feedback_service
    client = TestClient(app)

    response = client.post(
        "/feedback",
        data={
            "category": "forslag",
            "name": "System User",
            "email": "admin.user@example.test",
            "message": "Legg til bedre søk.",
            "page": "/volunteers",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Melding sendt." in response.text
    assert feedback_service.calls == [
        {
            "category": "forslag",
            "name": "System User",
            "email": "admin.user@example.test",
            "message": "Legg til bedre søk.",
            "page": "/volunteers",
            "source_key": "testclient",
        }
    ]


def test_feedback_submit_shows_error_when_linear_delivery_fails() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_feedback_service] = lambda: FailingFeedbackService()
    client = TestClient(app)

    response = client.post(
        "/feedback",
        data={
            "category": "forslag",
            "name": "System User",
            "email": "admin.user@example.test",
            "message": "Legg til bedre søk.",
            "page": "/volunteers",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Kunne ikke sende melding akkurat nå." in response.text
    assert "Legg til bedre søk." in response.text


def test_feedback_submit_passes_client_ip_and_returns_429_when_rate_limited() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_feedback_service] = lambda: RateLimitedFeedbackService()
    client = TestClient(app)

    response = client.post(
        "/feedback",
        data={
            "category": "forslag",
            "name": "System User",
            "email": "admin.user@example.test",
            "message": "Legg til bedre søk.",
            "page": "/volunteers",
        },
        headers={"HX-Request": "true", "X-Forwarded-For": "203.0.113.10"},
    )

    assert response.status_code == 429
    assert "For mange tilbakemeldinger" in response.text
    assert "Legg til bedre søk." in response.text
