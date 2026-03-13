from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.cookies import sign_session_id
from app.auth.models import AuthenticatedUser, WebSession
from app.auth.roles import UserRole
from app.main import create_app


class FakeSessionStore:
    async def load_authenticated_user(self, session_id: str):
        return (
            WebSession(
                session_id=session_id,
                auth_user_id=uuid4(),
                user_account_id=5,
                expires_at=datetime.now(UTC) + timedelta(hours=12),
            ),
            AuthenticatedUser(
                auth_user_id=uuid4(),
                user_account_id=5,
                username="admin",
                email="admin.user@example.test",
                display_name="System User",
                role=UserRole.ADMIN,
            ),
        )

    async def delete_session(self, session_id: str) -> None:
        return None


class FakeSearchService:
    async def search_people(self, query):
        return [
            type(
                "Result",
                (),
                {
                    "person_id": 12,
                    "first_name": "Sample",
                    "last_name": "Person",
                    "full_name": "Sample Person",
                    "pingvin_points": 8,
                    "last_semester_code": 20262,
                    "last_semester_label": "Fall 2026",
                    "birth_date": None,
                    "phone": "00000000",
                    "email": "person.one@example.test",
                },
            )()
        ]


def test_search_api_returns_english_results() -> None:
    app = create_app()
    app.state.session_store = FakeSessionStore()
    app.state.search_service = FakeSearchService()
    client = TestClient(app)
    client.cookies.set("kvarteret_session", sign_session_id("session-123"))

    response = client.post(
        "/api/v1/search/people",
        json={"include_groups": {"ids": [10, 12], "conjunction": False}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["full_name"] == "Sample Person"
    assert payload[0]["pingvin_points"] == 8
