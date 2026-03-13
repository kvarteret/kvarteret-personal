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
        return await self.get_invitation_by_token("token-123")

    async def get_invitation_by_token(self, token: str) -> PendingRegistrationDetail | None:
        if token != "token-123":
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

    async def submit_registration(self, token, submission):
        return await self.get_invitation_by_token(token)

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


def test_registration_pages_render() -> None:
    app = create_app()
    app.state.registrations_service = FakeRegistrationsService()
    app.state.session_store = FakeSessionStore()
    client = TestClient(app)
    client.cookies.set("kvarteret_session", sign_session_id("session-123"))

    admin_response = client.get("/registrations")
    public_response = client.get("/register/token-123")

    assert admin_response.status_code == 200
    assert "Pending registrations" in admin_response.text
    assert public_response.status_code == 200
    assert "Complete your details" in public_response.text
