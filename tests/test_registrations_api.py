from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.cookies import sign_session_id
from app.auth.models import AuthenticatedUser, WebSession
from app.auth.roles import UserRole
from app.main import create_app
from app.services.registrations import PendingRegistrationDetail, PendingRegistrationItem, RegistrationInvite


class FakeRegistrationsService:
    async def create_invitation(self, email: str) -> RegistrationInvite:
        return RegistrationInvite(7, "token-123", email, datetime(2026, 3, 13, tzinfo=UTC))

    async def list_pending(self) -> list[PendingRegistrationItem]:
        return [
            PendingRegistrationItem(
                registration_id=7,
                token="token-123",
                email="registrant@example.com",
                created_at=datetime(2026, 3, 13, tzinfo=UTC),
                submitted=True,
                first_name="Sample",
                last_name="Registrant",
                phone="00000000",
            )
        ]

    async def get_pending_detail(self, registration_id: int) -> PendingRegistrationDetail | None:
        if registration_id != 7:
            return None
        return PendingRegistrationDetail(
            registration_id=7,
            token="token-123",
            email="registrant@example.com",
            created_at=datetime(2026, 3, 13, tzinfo=UTC),
            submitted=True,
            pending_person_id=8,
            first_name="Sample",
            last_name="Registrant",
            phone="00000000",
            birth_date=date(1815, 12, 10),
            gender="K",
            address="Example address",
            postal_code="0000",
            employment_status=1,
        )

    async def get_invitation_by_token(self, token: str) -> PendingRegistrationDetail | None:
        return await self.get_pending_detail(7) if token == "token-123" else None

    async def submit_registration(self, token, submission):
        return await self.get_pending_detail(7)

    async def approve_registration(self, registration_id: int) -> int:
        return 12

    async def reject_registration(self, registration_id: int) -> None:
        return None


class FakeSessionStore:
    async def load_authenticated_user(self, session_id: str):
        return (
            WebSession(session_id=session_id, auth_user_id=uuid4(), user_account_id=5, expires_at=datetime.now(UTC) + timedelta(hours=12)),
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


def _make_client() -> TestClient:
    app = create_app()
    app.state.registrations_service = FakeRegistrationsService()
    app.state.session_store = FakeSessionStore()
    client = TestClient(app)
    client.cookies.set("kvarteret_session", sign_session_id("session-123"))
    return client


def test_registrations_api_lists_and_creates_invites() -> None:
    client = _make_client()

    list_response = client.get("/api/v1/registrations")
    create_response = client.post("/api/v1/registrations", json={"email": "registrant@example.com"})

    assert list_response.status_code == 200
    assert list_response.json()[0]["submitted"] is True
    assert create_response.status_code == 200
    assert create_response.json()["token"] == "token-123"


def test_registrations_api_handles_public_submission_and_approval() -> None:
    client = _make_client()

    public_response = client.post(
        "/api/v1/registration-submissions/token-123",
        json={"first_name": "Sample", "last_name": "Registrant", "gender": "K"},
    )
    approve_response = client.post("/api/v1/registrations/7/approve")

    assert public_response.status_code == 200
    assert public_response.json()["email"] == "registrant@example.com"
    assert approve_response.status_code == 200
    assert approve_response.json()["person_id"] == 12
