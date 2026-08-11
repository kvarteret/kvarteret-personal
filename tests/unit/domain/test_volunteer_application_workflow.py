from __future__ import annotations

import pytest

from app.domain.volunteer_applications.workflow import VolunteerApplicationWorkflow
from app.email_delivery import (
    APPLICANT_APPLICATION_RECEIVED,
    APPLICANT_INVITATION,
    APPLICANT_PROFILE_COMPLETION,
    EmailDeliveryRequest,
)


class _Record:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class FakeWorkflowOperations:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.detail_status = "trial"

    async def create_public_prospect_registration_record(
        self, registration, *, base_url: str | None
    ):
        self.calls.append(("register", base_url))
        return _Record(
            detail=_Record(registration_id=7, email="applicant@example.test"),
            friend_invites=[],
        )

    async def create_invitation_record(
        self,
        email: str,
        *,
        initial_group_id: int | None,
        initial_role_id: int | None,
    ):
        self.calls.append(("invite", email))
        return _Record(registration_id=7, email=email, token="token-123")

    async def submit_application_record(
        self,
        token: str,
        submission,
        *,
        base_url: str | None,
        photo_filename: str | None,
        photo_content: bytes | None,
        photo_content_type: str | None,
    ):
        self.calls.append(("submit", token))
        return _Record(registration_id=7, email="applicant@example.test")

    async def set_application_status_record(
        self, registration_id: int, *, status, start_trial: bool = False
    ):
        self.calls.append(("status", status.value))
        self.detail_status = status.value
        return _Record(
            registration_id=registration_id,
            status=status.value,
            email="applicant@example.test",
        )

    async def approve_application_record(
        self, registration_id: int, *, accepted_group_id: int | None
    ):
        self.calls.append(("approve", registration_id))
        return _Record(
            registration_id=registration_id,
            email="applicant@example.test",
        ), 12

    async def drop_group_invitee_record(
        self, registration_id: int, *, dropped_by_user_id: int | None
    ):
        self.calls.append(("drop", registration_id))
        return _Record(registration_id=registration_id)

    async def delete_application_record(self, registration_id: int):
        self.calls.append(("delete", registration_id))
        return _Record(
            registration_id=registration_id, email="applicant@example.test"
        )

    async def resend_invitation_record(self, registration_id: int):
        self.calls.append(("resend", registration_id))
        return _Record(registration_id=registration_id, email="applicant@example.test")

    async def get_volunteer_application_detail(self, registration_id: int):
        self.calls.append(("get", registration_id))
        return _Record(
            registration_id=registration_id,
            status=self.detail_status,
            email="applicant@example.test",
            pending_volunteer_id=8,
            group_id=None,
            group_status=None,
            group_members=None,
            is_part_of_active_group=False,
        )

    async def get_volunteer_application_by_token(self, token: str):
        self.calls.append(("get_by_token", token))
        return _Record(
            registration_id=7,
            status="new",
            email="applicant@example.test",
            pending_volunteer_id=None,
            group_id=None,
            group_status=None,
            group_members=None,
            is_part_of_active_group=False,
        )

    async def list_active_group_members(self, group_id: int):
        self.calls.append(("list_members", group_id))
        return []

    async def append_domain_event(self, event, *, subject_id: int):
        self.events = getattr(self, "events", [])
        self.events.append((event.event_type, subject_id))
        return len(self.events)


class FakeEmailOutbox:
    def __init__(self, *, fail_dispatch: bool = False) -> None:
        self.fail_dispatch = fail_dispatch
        self.requests: list[EmailDeliveryRequest] = []
        self.dispatch_count = 0

    async def enqueue(self, request: EmailDeliveryRequest):
        self.requests.append(request)
        return object()

    async def dispatch_due(self, *, batch_size: int = 10):
        self.dispatch_count += 1
        if self.fail_dispatch:
            raise RuntimeError("dispatch failed")
        return None


class FakeWorkflowSideEffects:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def after_public_prospect_registered(self, result, *, base_url: str | None):
        self.calls.append(("after_register", base_url))

    async def after_invited(self, invite, *, base_url: str | None):
        self.calls.append(("after_invited", invite.email))

    async def after_submitted(self, detail):
        self.calls.append(("after_submitted", detail.registration_id))

    async def after_trial_started(self, detail, *, base_url: str | None):
        self.calls.append(("after_trial", detail.registration_id))

    async def after_approved(self, detail, *, volunteer_id: int, base_url: str | None):
        self.calls.append(("after_approved", volunteer_id))

    async def after_group_invitee_dropped(self, detail):
        self.calls.append(("after_drop", detail.registration_id))

    async def after_deleted(self, detail):
        self.calls.append(("after_deleted", detail.registration_id))

    async def after_invitation_resent(self, detail, *, base_url: str | None):
        self.calls.append(("after_resend", detail.registration_id))


@pytest.mark.asyncio
async def test_workflow_submit_coordinates_record_then_side_effect() -> None:
    operations = FakeWorkflowOperations()
    side_effects = FakeWorkflowSideEffects()
    email_outbox = FakeEmailOutbox()
    workflow = VolunteerApplicationWorkflow(
        operations=operations,
        side_effects=side_effects,
        email_outbox=email_outbox,
    )

    detail = await workflow.submit(
        "token-123",
        object(),
        base_url="https://personal.example.test",
        photo_filename=None,
        photo_content=None,
        photo_content_type=None,
    )

    assert detail.registration_id == 7
    assert operations.calls == [("get_by_token", "token-123"), ("submit", "token-123")]
    assert side_effects.calls == [("after_submitted", 7)]
    assert operations.events == [("application_submitted", 7)]


@pytest.mark.asyncio
async def test_workflow_approve_coordinates_record_then_side_effect() -> None:
    operations = FakeWorkflowOperations()
    side_effects = FakeWorkflowSideEffects()
    workflow = VolunteerApplicationWorkflow(
        operations=operations,
        side_effects=side_effects,
        email_outbox=FakeEmailOutbox(),
    )

    volunteer_id = await workflow.approve(
        7, accepted_group_id=3, base_url="https://personal.example.test"
    )

    assert volunteer_id == 12
    assert operations.calls == [("get", 7), ("approve", 7)]
    assert side_effects.calls == [("after_approved", 12)]
    assert operations.events == [("application_approved", 7)]


@pytest.mark.asyncio
async def test_workflow_invite_survives_immediate_dispatch_failure() -> None:
    operations = FakeWorkflowOperations()
    side_effects = FakeWorkflowSideEffects()
    email_outbox = FakeEmailOutbox(fail_dispatch=True)
    workflow = VolunteerApplicationWorkflow(
        operations=operations,
        side_effects=side_effects,
        email_outbox=email_outbox,
    )

    invite = await workflow.invite(
        "new@example.test",
        base_url="https://personal.example.test",
        initial_group_id=None,
        initial_role_id=None,
    )

    assert invite.registration_id == 7
    assert operations.calls == [("invite", "new@example.test")]
    assert side_effects.calls == [("after_invited", "new@example.test")]
    assert len(email_outbox.requests) == 1
    assert email_outbox.dispatch_count == 1


@pytest.mark.asyncio
async def test_workflow_register_mark_delete_and_resend_are_traceable() -> None:
    operations = FakeWorkflowOperations()
    side_effects = FakeWorkflowSideEffects()
    email_outbox = FakeEmailOutbox()
    workflow = VolunteerApplicationWorkflow(
        operations=operations,
        side_effects=side_effects,
        email_outbox=email_outbox,
    )

    await workflow.register_public_prospect(
        object(), base_url="https://personal.example.test"
    )
    operations.detail_status = "new"
    await workflow.contact(7)
    await workflow.start_trial(7, base_url="https://personal.example.test")
    operations.detail_status = "new"
    await workflow.delete(7)
    operations.detail_status = "new"
    await workflow.resend_invitation(7, base_url="https://personal.example.test")

    assert operations.calls == [
        ("register", "https://personal.example.test"),
        ("get", 7),
        ("status", "contacted"),
        ("get", 7),
        ("status", "trial"),
        ("get", 7),
        ("delete", 7),
        ("get", 7),
        ("resend", 7),
    ]
    assert side_effects.calls == [
        ("after_register", "https://personal.example.test"),
        ("after_trial", 7),
        ("after_deleted", 7),
        ("after_resend", 7),
    ]
    assert [request.template_key for request in email_outbox.requests] == [
        APPLICANT_APPLICATION_RECEIVED,
        APPLICANT_PROFILE_COMPLETION,
        APPLICANT_INVITATION,
    ]
