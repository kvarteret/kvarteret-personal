"""Workflow coordinator for the volunteer application lifecycle.

Every lifecycle action follows the same shape:

1. load the typed record,
2. ask the pure state machine whether the transition is legal
   (``IllegalTransition`` propagates to the service layer, which maps
   it onto ``VolunteerApplicationConflictError``),
3. persist the change through the operations protocol,
4. append the domain event row in the same request transaction,
5. commit the unit of work,
6. execute the named side effects (email, cache, storage cleanup).

Step 5 before step 6 is the commit-before-effect rule: no email may
announce a state the database can still roll back. Group approval
promotes every active member inside one transaction (steps 2-4 per
member, then a single commit), which makes it atomic and all-or-nothing.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Protocol

from app.db.session import commit_request_session
from app.domain.volunteer_applications.state_machine import (
    ApplicationAction,
    ApplicationState,
    DomainEventRecord,
    MembershipState,
    TransitionContext,
    application_transition,
    membership_transition,
)

if TYPE_CHECKING:
    from app.domain.volunteer_applications.service import (
        PublicProspectRegistrationInput,
        PublicProspectRegistrationResult,
        VolunteerApplicationDetail,
        VolunteerApplicationGroupMember,
        VolunteerApplicationInvite,
        VolunteerApplicationSubmissionInput,
    )


class VolunteerApplicationWorkflowOperations(Protocol):
    async def create_public_prospect_registration_record(
        self,
        registration: "PublicProspectRegistrationInput",
        *,
        base_url: str | None,
    ) -> "PublicProspectRegistrationResult": ...
    async def create_invitation_record(
        self,
        email: str,
        *,
        initial_group_id: int | None,
        initial_role_id: int | None,
    ) -> "VolunteerApplicationInvite": ...
    async def submit_application_record(
        self,
        token: str,
        submission: "VolunteerApplicationSubmissionInput",
        *,
        base_url: str | None,
        photo_filename: str | None,
        photo_content: bytes | None,
        photo_content_type: str | None,
    ) -> "VolunteerApplicationDetail": ...
    async def mark_trial_shift_attended_record(
        self, registration_id: int, *, attended: bool
    ) -> "VolunteerApplicationDetail": ...
    async def approve_application_record(
        self, registration_id: int, *, accepted_group_id: int | None
    ) -> "tuple[VolunteerApplicationDetail, int]": ...
    async def drop_group_invitee_record(
        self, registration_id: int, *, dropped_by_user_id: int | None
    ) -> "VolunteerApplicationDetail": ...
    async def delete_application_record(
        self, registration_id: int
    ) -> "VolunteerApplicationDetail": ...
    async def resend_invitation_record(
        self, registration_id: int
    ) -> "VolunteerApplicationInvite": ...
    async def get_volunteer_application_detail(
        self, registration_id: int
    ) -> "VolunteerApplicationDetail | None": ...
    async def get_volunteer_application_by_token(
        self, token: str
    ) -> "VolunteerApplicationDetail | None": ...
    async def list_active_group_members(
        self, group_id: int
    ) -> "list[VolunteerApplicationGroupMember]": ...
    async def append_domain_event(
        self, event: DomainEventRecord, *, subject_id: int
    ) -> None: ...


class VolunteerApplicationSideEffectsProtocol(Protocol):
    async def after_public_prospect_registered(
        self, result: "PublicProspectRegistrationResult", *, base_url: str | None
    ) -> None: ...
    async def after_invited(
        self, invite: "VolunteerApplicationInvite", *, base_url: str | None
    ) -> None: ...
    async def after_submitted(
        self, detail: "VolunteerApplicationDetail",
    ) -> None: ...
    async def after_trial_shift_marked(
        self, detail: "VolunteerApplicationDetail",
    ) -> None: ...
    async def after_approved(
        self,
        detail: "VolunteerApplicationDetail",
        *,
        volunteer_id: int,
        base_url: str | None,
    ) -> None: ...
    async def after_group_invitee_dropped(
        self, detail: "VolunteerApplicationDetail",
    ) -> None: ...
    async def after_deleted(
        self, detail: "VolunteerApplicationDetail",
    ) -> None: ...
    async def after_invitation_resent(
        self, detail: "VolunteerApplicationInvite", *, base_url: str | None
    ) -> None: ...


def _approval_context(
    detail: "VolunteerApplicationDetail",
    *,
    actor_user_account_id: int | None,
    as_group_action: bool,
) -> TransitionContext:
    return TransitionContext(
        actor_user_account_id=actor_user_account_id,
        is_part_of_active_group=(
            False if as_group_action else detail.is_part_of_active_group
        ),
        has_submission=detail.pending_volunteer_id is not None,
    )


class VolunteerApplicationWorkflow:
    def __init__(
        self,
        *,
        operations: VolunteerApplicationWorkflowOperations,
        side_effects: VolunteerApplicationSideEffectsProtocol,
    ) -> None:
        self.operations = operations
        self.side_effects = side_effects

    async def invite(
        self,
        email: str,
        *,
        base_url: str | None,
        initial_group_id: int | None,
        initial_role_id: int | None,
        actor_user_account_id: int | None = None,
    ) -> "VolunteerApplicationInvite":
        invite = await self.operations.create_invitation_record(
            email,
            initial_group_id=initial_group_id,
            initial_role_id=initial_role_id,
        )
        # Creation is not a transition; the audit row is appended directly.
        await self.operations.append_domain_event(
            DomainEventRecord(
                event_type="application_invited",
                actor_user_account_id=actor_user_account_id,
                subject_type="application",
                subject_id=invite.registration_id,
                payload={"email": invite.email},
            ),
            subject_id=invite.registration_id,
        )
        await commit_request_session()
        try:
            await self.side_effects.after_invited(invite, base_url=base_url)
        except Exception:
            await self.operations.delete_application_record(invite.registration_id)
            await commit_request_session()
            raise
        return invite

    async def register_public_prospect(
        self,
        registration: "PublicProspectRegistrationInput",
        *,
        base_url: str | None,
    ) -> "VolunteerApplicationDetail":
        result = await self.operations.create_public_prospect_registration_record(
            registration, base_url=base_url
        )
        await self.operations.append_domain_event(
            DomainEventRecord(
                event_type="prospect_registered",
                actor_user_account_id=None,
                subject_type="application",
                subject_id=result.detail.registration_id,
                payload={
                    "email": result.detail.email,
                    "friend_invites": [
                        invite.registration_id for invite in result.friend_invites
                    ],
                },
            ),
            subject_id=result.detail.registration_id,
        )
        for invite in result.friend_invites:
            await self.operations.append_domain_event(
                DomainEventRecord(
                    event_type="application_invited",
                    actor_user_account_id=None,
                    subject_type="application",
                    subject_id=invite.registration_id,
                    payload={
                        "email": invite.email,
                        "invited_by_registration_id": result.detail.registration_id,
                    },
                ),
                subject_id=invite.registration_id,
            )
        await commit_request_session()
        await self.side_effects.after_public_prospect_registered(
            result, base_url=base_url
        )
        return result.detail

    async def submit(
        self,
        token: str,
        submission: "VolunteerApplicationSubmissionInput",
        *,
        base_url: str | None,
        photo_filename: str | None,
        photo_content: bytes | None,
        photo_content_type: str | None,
    ) -> "VolunteerApplicationDetail":
        existing = await self.operations.get_volunteer_application_by_token(token)
        result = None
        if existing is not None:
            result = application_transition(
                ApplicationState(existing.status),
                ApplicationAction.SUBMIT_PROFILE,
            )
        detail = await self.operations.submit_application_record(
            token,
            submission,
            base_url=base_url,
            photo_filename=photo_filename,
            photo_content=photo_content,
            photo_content_type=photo_content_type,
        )
        if result is not None and result.event is not None:
            await self.operations.append_domain_event(
                replace(result.event, subject_id=detail.registration_id),
                subject_id=detail.registration_id,
            )
        await commit_request_session()
        await self.side_effects.after_submitted(detail)
        return detail

    async def mark_trial_shift_attended(
        self,
        registration_id: int,
        *,
        attended: bool,
        actor_user_account_id: int | None = None,
    ) -> "VolunteerApplicationDetail":
        existing = await self.operations.get_volunteer_application_detail(
            registration_id
        )
        result = None
        if existing is not None:
            result = application_transition(
                ApplicationState(existing.status),
                ApplicationAction.MARK_TRIAL_SHIFT,
                context=TransitionContext(
                    actor_user_account_id=actor_user_account_id
                ),
            )
        detail = await self.operations.mark_trial_shift_attended_record(
            registration_id, attended=attended
        )
        if result is not None and result.event is not None:
            event = replace(
                result.event,
                payload={**result.event.payload, "attended": attended},
            )
            await self.operations.append_domain_event(
                event, subject_id=registration_id
            )
        await commit_request_session()
        await self.side_effects.after_trial_shift_marked(detail)
        return detail

    async def approve(
        self,
        registration_id: int,
        *,
        accepted_group_id: int | None,
        base_url: str | None,
        actor_user_account_id: int | None = None,
    ) -> int:
        detail, volunteer_id, event = await self._approve_one(
            registration_id,
            accepted_group_id=accepted_group_id,
            actor_user_account_id=actor_user_account_id,
            as_group_action=False,
        )
        await commit_request_session()
        await self.side_effects.after_approved(
            detail, volunteer_id=volunteer_id, base_url=base_url
        )
        return volunteer_id

    async def approve_group(
        self,
        registration_ids: list[int],
        *,
        accepted_group_id: int,
        base_url: str | None,
        actor_user_account_id: int | None = None,
    ) -> list[int]:
        """Promote every member in one transaction: all or none.

        Database writes for all members happen before the single commit;
        a failure on any member rolls back every promotion. Emails go
        out only after the commit succeeds.
        """
        approved: list[tuple["VolunteerApplicationDetail", int]] = []
        for registration_id in registration_ids:
            detail, volunteer_id, _ = await self._approve_one(
                registration_id,
                accepted_group_id=accepted_group_id,
                actor_user_account_id=actor_user_account_id,
                as_group_action=True,
            )
            approved.append((detail, volunteer_id))
        await commit_request_session()
        for detail, volunteer_id in approved:
            await self.side_effects.after_approved(
                detail, volunteer_id=volunteer_id, base_url=base_url
            )
        return [volunteer_id for _, volunteer_id in approved]

    async def _approve_one(
        self,
        registration_id: int,
        *,
        accepted_group_id: int | None,
        actor_user_account_id: int | None,
        as_group_action: bool,
    ) -> "tuple[VolunteerApplicationDetail, int, DomainEventRecord | None]":
        existing = await self.operations.get_volunteer_application_detail(
            registration_id
        )
        result = None
        if existing is not None:
            result = application_transition(
                ApplicationState(existing.status),
                ApplicationAction.APPROVE,
                context=_approval_context(
                    existing,
                    actor_user_account_id=actor_user_account_id,
                    as_group_action=as_group_action,
                ),
            )
        detail, volunteer_id = await self.operations.approve_application_record(
            registration_id, accepted_group_id=accepted_group_id
        )
        event = None
        if result is not None and result.event is not None:
            event = replace(
                result.event,
                subject_id=registration_id,
                payload={
                    **result.event.payload,
                    "volunteer_id": volunteer_id,
                    "group_action": as_group_action,
                },
            )
            await self.operations.append_domain_event(
                event, subject_id=registration_id
            )
        return detail, volunteer_id, event

    async def drop_group_invitee(
        self,
        registration_id: int,
        *,
        dropped_by_user_id: int | None,
    ) -> None:
        existing = await self.operations.get_volunteer_application_detail(
            registration_id
        )
        result = None
        if existing is not None and existing.group_status is not None:
            result = membership_transition(
                MembershipState(existing.group_status),
                ApplicationAction.DROP_MEMBER,
                context=TransitionContext(
                    actor_user_account_id=dropped_by_user_id
                ),
            )
        detail = await self.operations.drop_group_invitee_record(
            registration_id, dropped_by_user_id=dropped_by_user_id
        )
        if result is not None and result.event is not None:
            await self.operations.append_domain_event(
                replace(result.event, subject_id=registration_id),
                subject_id=registration_id,
            )
        await commit_request_session()
        await self.side_effects.after_group_invitee_dropped(detail)

    async def delete(
        self,
        registration_id: int,
        *,
        actor_user_account_id: int | None = None,
    ) -> None:
        existing = await self.operations.get_volunteer_application_detail(
            registration_id
        )
        result = None
        if existing is not None:
            result = application_transition(
                ApplicationState(existing.status),
                ApplicationAction.DELETE,
                context=TransitionContext(
                    actor_user_account_id=actor_user_account_id
                ),
            )
        detail = await self.operations.delete_application_record(registration_id)
        if result is not None and result.event is not None:
            await self.operations.append_domain_event(
                replace(
                    result.event,
                    subject_id=registration_id,
                    payload={
                        **result.event.payload,
                        "email": detail.email,
                    },
                ),
                subject_id=registration_id,
            )
        await commit_request_session()
        await self.side_effects.after_deleted(detail)

    async def resend_invitation(
        self,
        registration_id: int,
        *,
        base_url: str | None,
        actor_user_account_id: int | None = None,
    ) -> "VolunteerApplicationInvite":
        existing = await self.operations.get_volunteer_application_detail(
            registration_id
        )
        result = None
        if existing is not None:
            result = application_transition(
                ApplicationState(existing.status),
                ApplicationAction.RESEND_INVITATION,
                context=TransitionContext(
                    actor_user_account_id=actor_user_account_id
                ),
            )
        detail = await self.operations.resend_invitation_record(registration_id)
        if result is not None and result.event is not None:
            await self.operations.append_domain_event(
                replace(result.event, subject_id=registration_id),
                subject_id=registration_id,
            )
        await commit_request_session()
        await self.side_effects.after_invitation_resent(detail, base_url=base_url)
        return detail
