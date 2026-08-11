from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.auth.roles import UserRole
from app.dependencies import get_email_outbox_service
from app.email_delivery import (
    DispatchSummary,
    EmailDeliveryAttemptItem,
    EmailDeliveryDetail,
    EmailDeliveryListItem,
)
from app.main import create_app
from tests.support.helpers import make_authenticated_user, override_authenticated_user

DELIVERY_ID = UUID("11111111-1111-4111-8111-111111111111")
SUCCESSOR_ID = UUID("22222222-2222-4222-8222-222222222222")


class FakeEmailOutboxService:
    def __init__(self) -> None:
        self.retry_calls: list[tuple[UUID, int]] = []
        self.correction_calls: list[tuple[UUID, str, int]] = []

    def _delivery(self) -> EmailDeliveryListItem:
        now = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
        return EmailDeliveryListItem(
            delivery_id=DELIVERY_ID,
            template_key="applicant_profile_completion",
            masked_recipient="s********@example.test",
            business_type="volunteer_application",
            business_id="42",
            registration_id=42,
            status="failed",
            automatic_attempt_count=1,
            last_error_category="smtp_permanent",
            next_attempt_at=now,
            enqueued_trace_id="a" * 32,
            created_at=now,
            updated_at=now,
            sent_at=None,
            supersedes_delivery_id=None,
        )

    async def list_deliveries(self, **_kwargs):
        return [self._delivery()]

    async def get_delivery(self, delivery_id: UUID):
        if delivery_id != DELIVERY_ID:
            return None
        delivery = self._delivery()
        return EmailDeliveryDetail(
            delivery=delivery,
            attempts=(
                EmailDeliveryAttemptItem(
                    attempt_no=1,
                    stage="smtp",
                    outcome="permanent_failure",
                    error_category="smtp_permanent",
                    smtp_status=550,
                    smtp_status_class=5,
                    duration_ms=12,
                    started_at=delivery.created_at,
                    finished_at=delivery.updated_at,
                ),
            ),
        )

    async def retry_failed(self, delivery_id: UUID, *, actor_user_account_id: int):
        self.retry_calls.append((delivery_id, actor_user_account_id))
        return SUCCESSOR_ID

    async def correct_volunteer_recipient(
        self,
        delivery_id: UUID,
        *,
        recipient_email: str,
        actor_user_account_id: int,
    ):
        self.correction_calls.append(
            (delivery_id, recipient_email, actor_user_account_id)
        )
        return SUCCESSOR_ID

    async def dispatch_due(self, **_kwargs):
        return DispatchSummary(1, 1, 0, 0, 0, 0, (SUCCESSOR_ID,))


def _client(monkeypatch, *, role: UserRole = UserRole.ADMIN):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    app = create_app()
    override_authenticated_user(app, make_authenticated_user(role))
    service = FakeEmailOutboxService()
    app.dependency_overrides[get_email_outbox_service] = lambda: service
    return TestClient(app), service


def test_admin_can_list_and_inspect_masked_delivery(monkeypatch) -> None:
    client, _service = _client(monkeypatch)

    listing = client.get("/email-deliveries")
    detail = client.get(f"/email-deliveries/{DELIVERY_ID}")

    assert listing.status_code == 200
    assert detail.status_code == 200
    assert "s********@example.test" in listing.text
    assert "smtp_permanent" in detail.text
    assert "synthetic@example.test" not in detail.text
    assert "Forsøkshistorikk" in detail.text


def test_non_admin_cannot_view_delivery_history(monkeypatch) -> None:
    client, _service = _client(monkeypatch, role=UserRole.GROUP_ADMIN)

    assert client.get("/email-deliveries").status_code == 403


def test_retry_creates_successor_and_redirects(monkeypatch) -> None:
    client, service = _client(monkeypatch)

    response = client.post(
        f"/email-deliveries/{DELIVERY_ID}/retry", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/email-deliveries/{SUCCESSOR_ID}"
    assert service.retry_calls == [(DELIVERY_ID, 5)]


def test_recipient_correction_passes_new_address_without_rendering_it(monkeypatch) -> None:
    client, service = _client(monkeypatch)

    response = client.post(
        f"/email-deliveries/{DELIVERY_ID}/correct-recipient",
        data={"recipient_email": "corrected@example.test"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert service.correction_calls == [(DELIVERY_ID, "corrected@example.test", 5)]


def test_session_backed_post_requires_csrf_token(monkeypatch) -> None:
    client, service = _client(monkeypatch)
    client.cookies.set("kvarteret_session", "invalid-but-present")

    response = client.post(f"/email-deliveries/{DELIVERY_ID}/retry")

    assert response.status_code == 403
    assert service.retry_calls == []
