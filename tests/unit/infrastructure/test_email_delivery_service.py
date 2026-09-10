from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.metadata import public_metadata
from app.db.session import reset_request_session, set_request_session
from app.domain.admin_accounts.tables import user_accounts
from app.domain.volunteer_applications.tables import (
    domain_events,
    volunteer_application_friend_invitations,
    volunteer_application_invites,
    volunteer_application_submissions,
)
from app.domain.volunteers.tables import volunteer_records
from app.email_delivery import (
    APPLICANT_APPLICATION_RECEIVED,
    APPLICANT_FRIEND_INVITATION,
    APPLICANT_INVITATION,
    EmailDeliveryRequest,
)
from app.email_outbox_service import EmailOutboxService
from app.infrastructure.email.smtp import SmtpDeliveryError
from app.db.table_defs.email_delivery import email_deliveries, email_delivery_attempts


class FakeSender:
    def __init__(self, errors: list[Exception | None] | None = None) -> None:
        self.errors = list(errors or [])
        self.sent = 0

    async def send_email(self, **_kwargs) -> None:
        error = self.errors.pop(0) if self.errors else None
        if error is not None:
            raise error
        self.sent += 1


class FakeApplicantRenderer:
    def __init__(self) -> None:
        self.friend_calls: list[dict[str, str]] = []

    def render_application_received_email(self):
        return Rendered()

    def render_invitation_email(self, **_kwargs):
        return Rendered()

    def render_friend_invitation_email(self, **kwargs):
        self.friend_calls.append(kwargs)
        return Rendered()


class Rendered:
    subject = "Subject"
    html_body = "<p>Body</p>"


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        execution_options={"schema_translate_map": {"public": None}},
    )
    tables = [
        user_accounts,
        volunteer_records,
        volunteer_application_invites,
        volunteer_application_friend_invitations,
        volunteer_application_submissions,
        domain_events,
        email_deliveries,
        email_delivery_attempts,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: public_metadata.create_all(
                sync_connection, tables=tables
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        token = set_request_session(value)
        try:
            yield value
        finally:
            reset_request_session(token)
    await engine.dispose()


def _service(sender: FakeSender, clock: Clock) -> EmailOutboxService:
    return EmailOutboxService(
        settings=Settings(
            app_secret_key="test-secret",
            app_public_base_url="https://personal.example.test",
        ),
        email_sender=sender,
        applicant_renderer=FakeApplicantRenderer(),  # type: ignore[arg-type]
        now=clock,
    )


async def _seed_application(session) -> None:
    await session.execute(
        insert(volunteer_application_invites).values(
            id=7,
            token=str(uuid4()),
            email="synthetic@example.test",
            source="admin_invite",
            status="invited",
            trial_shift_attended=False,
            created_at=datetime.now(UTC),
        )
    )


async def _seed_friend_applications(session) -> None:
    await session.execute(
        insert(volunteer_application_invites),
        [
            {
                "id": 6,
                "token": str(uuid4()),
                "email": "inviter@example.test",
                "source": "public_signup",
                "status": "trial",
                "trial_shift_attended": False,
                "created_at": datetime.now(UTC),
            },
            {
                "id": 7,
                "token": "friend-token",
                "email": "friend@example.test",
                "source": "friend_invite",
                "status": "new",
                "trial_shift_attended": False,
                "created_at": datetime.now(UTC),
            },
        ],
    )
    await session.execute(
        insert(volunteer_application_submissions).values(
            id=1,
            invite_id=6,
            first_name="Current",
            last_name="Inviter",
            email="inviter@example.test",
            gender="A",
            created_at=datetime.now(UTC),
        )
    )
    await session.execute(
        insert(volunteer_application_friend_invitations).values(
            id=1,
            inviter_application_id=6,
            invitee_application_id=7,
            inviter_name_snapshot="Snapshot Inviter",
            inviter_email_snapshot="inviter@example.test",
            invitee_email_snapshot="friend@example.test",
            created_at=datetime.now(UTC),
        )
    )


async def _enqueue(service: EmailOutboxService) -> object:
    return await service.enqueue(
        EmailDeliveryRequest(
            template_key=APPLICANT_INVITATION,
            template_version=1,
            recipient_email="synthetic@example.test",
            business_type="volunteer_application",
            business_id="7",
            idempotency_key="application:7:invitation:v1",
            registration_id=7,
        )
    )


async def _enqueue_application_receipt(service: EmailOutboxService) -> object:
    return await service.enqueue(
        EmailDeliveryRequest(
            template_key=APPLICANT_APPLICATION_RECEIVED,
            template_version=1,
            recipient_email="synthetic@example.test",
            business_type="volunteer_application",
            business_id="7",
            idempotency_key="application:7:received:v1",
            registration_id=7,
        )
    )


@pytest.mark.asyncio
async def test_enqueue_is_idempotent_and_success_records_attempt(session) -> None:
    await _seed_application(session)
    clock = Clock()
    sender = FakeSender()
    service = _service(sender, clock)

    delivery_id = await _enqueue(service)
    assert await _enqueue(service) == delivery_id
    await session.commit()

    summary = await service.dispatch_due()

    assert summary.sent_count == 1
    assert sender.sent == 1
    delivery = (
        (
            await session.execute(
                select(email_deliveries).where(email_deliveries.c.id == delivery_id)
            )
        )
        .mappings()
        .one()
    )
    attempt = (
        (
            await session.execute(
                select(email_delivery_attempts).where(
                    email_delivery_attempts.c.delivery_id == delivery_id
                )
            )
        )
        .mappings()
        .one()
    )
    assert delivery["status"] == "sent"
    assert delivery["sent_at"].replace(tzinfo=UTC) == clock.value
    assert attempt["stage"] == "smtp"
    assert attempt["outcome"] == "succeeded"


@pytest.mark.asyncio
async def test_application_receipt_uses_existing_renderer_without_public_base_url(
    session,
) -> None:
    await _seed_application(session)
    clock = Clock()
    sender = FakeSender()
    service = EmailOutboxService(
        settings=Settings(app_secret_key="test-secret"),
        email_sender=sender,
        applicant_renderer=FakeApplicantRenderer(),  # type: ignore[arg-type]
        now=clock,
    )
    await _enqueue_application_receipt(service)
    await session.commit()

    summary = await service.dispatch_due()

    assert summary.sent_count == 1
    assert sender.sent == 1


@pytest.mark.asyncio
async def test_friend_invitation_uses_inviter_application_and_snapshot_fallback(session) -> None:
    await _seed_friend_applications(session)
    clock = Clock()
    sender = FakeSender()
    renderer = FakeApplicantRenderer()
    service = EmailOutboxService(
        settings=Settings(
            app_secret_key="test-secret",
            app_public_base_url="https://personal.example.test",
        ),
        email_sender=sender,
        applicant_renderer=renderer,  # type: ignore[arg-type]
        now=clock,
    )
    await service.enqueue(
        EmailDeliveryRequest(
            template_key=APPLICANT_FRIEND_INVITATION,
            template_version=1,
            recipient_email="friend@example.test",
            business_type="volunteer_application",
            business_id="7",
            idempotency_key="application:7:friend-invitation:v1",
            registration_id=7,
        )
    )
    await session.commit()

    summary = await service.dispatch_due()

    assert summary.sent_count == 1
    assert renderer.friend_calls == [
        {
            "invitation_url": "https://personal.example.test/apply/friend-token",
            "inviter_name": "Current Inviter",
        }
    ]


@pytest.mark.asyncio
async def test_retryable_smtp_failure_schedules_one_minute_retry(session) -> None:
    await _seed_application(session)
    clock = Clock()
    service = _service(
        FakeSender(
            [SmtpDeliveryError("smtp_temporary", retryable=True, smtp_status=451)]
        ),
        clock,
    )
    delivery_id = await _enqueue(service)
    await session.commit()

    summary = await service.dispatch_due()

    assert summary.retrying_count == 1
    delivery = (
        (
            await session.execute(
                select(email_deliveries).where(email_deliveries.c.id == delivery_id)
            )
        )
        .mappings()
        .one()
    )
    assert delivery["status"] == "pending"
    assert delivery["next_attempt_at"].replace(tzinfo=UTC) == clock.value + timedelta(
        minutes=1
    )
    assert delivery["last_error_category"] == "smtp_temporary"


@pytest.mark.asyncio
async def test_permanent_smtp_failure_is_visible_as_failed(session) -> None:
    await _seed_application(session)
    clock = Clock()
    service = _service(
        FakeSender(
            [SmtpDeliveryError("smtp_permanent", retryable=False, smtp_status=550)]
        ),
        clock,
    )
    delivery_id = await _enqueue(service)
    await session.commit()

    summary = await service.dispatch_due()

    assert summary.failed_count == 1
    detail = await service.get_delivery(delivery_id)  # type: ignore[arg-type]
    assert detail is not None
    assert detail.delivery.status == "failed"
    assert detail.delivery.masked_recipient == "s********@example.test"
    assert detail.attempts[0].smtp_status_class == 5


@pytest.mark.asyncio
async def test_expired_lease_marks_started_attempt_interrupted_before_reclaim(
    session,
) -> None:
    await _seed_application(session)
    clock = Clock()
    sender = FakeSender()
    service = _service(sender, clock)
    delivery_id = await _enqueue(service)
    await session.execute(
        email_deliveries.update()
        .where(email_deliveries.c.id == delivery_id)
        .values(lease_owner="lost", lease_until=clock.value - timedelta(seconds=1))
    )
    await session.execute(
        insert(email_delivery_attempts).values(
            delivery_id=delivery_id,
            attempt_no=1,
            stage="smtp",
            outcome="started",
            started_at=clock.value - timedelta(minutes=6),
        )
    )
    await session.execute(
        email_deliveries.update()
        .where(email_deliveries.c.id == delivery_id)
        .values(automatic_attempt_count=1)
    )
    await session.commit()

    summary = await service.dispatch_due()

    assert summary.interrupted_count == 1
    assert summary.sent_count == 1
    outcomes = list(
        (
            await session.execute(
                select(email_delivery_attempts.c.outcome)
                .where(email_delivery_attempts.c.delivery_id == delivery_id)
                .order_by(email_delivery_attempts.c.attempt_no)
            )
        ).scalars()
    )
    assert outcomes == ["interrupted", "succeeded"]


async def test_queued_occurrence_waits_for_real_commit_and_dies_on_rollback(session, caplog):
    import logging
    service = _service(FakeSender(), Clock())
    await _seed_application(session)
    await session.commit()
    def request(key):
        return EmailDeliveryRequest(
            template_key=APPLICANT_APPLICATION_RECEIVED,
            template_version=1,
            recipient_email="synthetic@example.test",
            business_type="volunteer_application",
            business_id="7",
            idempotency_key=key,
            registration_id=7,
        )
    with caplog.at_level(logging.INFO):
        await service.enqueue(request("rollback"))
        assert not [r for r in caplog.records if getattr(r, "event", None) == "email.delivery.queued"]
        await session.rollback()
        delivery = await service.enqueue(request("commit"))
        await session.commit()
        await session.commit()
    queued = [r for r in caplog.records if getattr(r, "event", None) == "email.delivery.queued"]
    assert len(queued) == 1
    assert queued[0].event_data["email_delivery_id"] == str(delivery)
    assert queued[0].event_data["event_id"] == f"kvarteret-personal:email.delivery.queued:{delivery}"
