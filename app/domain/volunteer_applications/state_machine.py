"""Pure, I/O-free volunteer application state machine.

Encodes the application lifecycle as explicit states, actions, and
transitions.  Every state/action pair is either legal (produces a
``TransitionResult``) or illegal (raises ``IllegalTransition``).

The application status is deliberately independent of whether the applicant
has completed every profile field. The five user-facing states are::

    new ──contact─────────────────────► contacted
    contacted ──start-trial───────────► trial
    trial ──promote───────────────────► volunteer
    {new,contacted,trial,volunteer} ──reject──► not_volunteer
    not_volunteer ──reopen────────────► contacted

``SUBMIT_PROFILE`` keeps the current lifecycle state. This lets a candidate
complete the profile after the trial has started without moving backwards.

Membership states (per group member)::

    active ──drop──► dropped

See ``docs/adr/003-domain-event-log.md`` for the audit design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


# ── Enums ──────────────────────────────────────────────────────────


class ApplicationState(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    TRIAL = "trial"
    VOLUNTEER = "volunteer"
    NOT_VOLUNTEER = "not_volunteer"


class MembershipState(StrEnum):
    ACTIVE = "active"
    DROPPED = "dropped"


class ApplicationAction(StrEnum):
    SUBMIT_PROFILE = "submit_profile"
    RESEND_INVITATION = "resend_invitation"
    CONTACT = "contact"
    START_TRIAL = "start_trial"
    PROMOTE = "promote"
    REJECT = "reject"
    REOPEN = "reopen"
    RESTORE_VOLUNTEER = "restore_volunteer"
    DELETE = "delete"
    DROP_MEMBER = "drop_member"


# ── Errors ─────────────────────────────────────────────────────────


class IllegalTransition(ValueError):
    """Raised when a transition is not allowed for the given state."""


# ── Transition table ───────────────────────────────────────────────

# Maps (current_state, action) → new_state.
# Only legal transitions are listed; anything else raises IllegalTransition.
_TRANSITIONS: dict[
    tuple[ApplicationState, ApplicationAction], ApplicationState
] = {
    **{
        (state, ApplicationAction.SUBMIT_PROFILE): state
        for state in (
            ApplicationState.NEW,
            ApplicationState.CONTACTED,
            ApplicationState.TRIAL,
            ApplicationState.VOLUNTEER,
        )
    },
    (ApplicationState.NEW, ApplicationAction.RESEND_INVITATION): ApplicationState.NEW,
    (ApplicationState.CONTACTED, ApplicationAction.RESEND_INVITATION): ApplicationState.CONTACTED,
    (ApplicationState.NEW, ApplicationAction.CONTACT): ApplicationState.CONTACTED,
    (ApplicationState.CONTACTED, ApplicationAction.START_TRIAL): ApplicationState.TRIAL,
    (ApplicationState.TRIAL, ApplicationAction.PROMOTE): ApplicationState.VOLUNTEER,
    (ApplicationState.NEW, ApplicationAction.REJECT): ApplicationState.NOT_VOLUNTEER,
    (ApplicationState.CONTACTED, ApplicationAction.REJECT): ApplicationState.NOT_VOLUNTEER,
    (ApplicationState.TRIAL, ApplicationAction.REJECT): ApplicationState.NOT_VOLUNTEER,
    (ApplicationState.VOLUNTEER, ApplicationAction.REJECT): ApplicationState.NOT_VOLUNTEER,
    (ApplicationState.NOT_VOLUNTEER, ApplicationAction.REOPEN): ApplicationState.CONTACTED,
    (ApplicationState.NOT_VOLUNTEER, ApplicationAction.RESTORE_VOLUNTEER): ApplicationState.VOLUNTEER,
}

# Actions that result in row removal (no target state).
_DELETE_ACTIONS = {ApplicationAction.DELETE}

# Membership transitions.
_MEMBERSHIP_TRANSITIONS: dict[
    tuple[MembershipState, ApplicationAction], MembershipState
] = {
    (MembershipState.ACTIVE, ApplicationAction.DROP_MEMBER): MembershipState.DROPPED,
}


# ── Side effects ───────────────────────────────────────────────────

# Side effects are named, serializable records so the workflow
# coordinator can execute them after the database transaction commits.
# This preserves today's commit-before-email behavior and keeps the
# seam open for the deferred transactional outbox.


@dataclass(frozen=True, slots=True)
class Effect:
    """Base class for named side effects."""
    pass


@dataclass(frozen=True, slots=True)
class SendApplicantEmail(Effect):
    template: str
    registration_id: int


@dataclass(frozen=True, slots=True)
class SendInvitationEmail(Effect):
    registration_id: int


@dataclass(frozen=True, slots=True)
class SendApprovalEmail(Effect):
    registration_id: int
    volunteer_id: int


@dataclass(frozen=True, slots=True)
class SendRejectionEmail(Effect):
    registration_id: int


# ── Domain event ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DomainEventRecord:
    event_type: str
    actor_user_account_id: int | None
    subject_type: str
    subject_id: int
    payload: dict
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Transition result ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TransitionResult:
    new_state: ApplicationState | MembershipState
    effects: tuple[Effect, ...] = ()
    event: DomainEventRecord | None = None


# ── Transition context ─────────────────────────────────────────────

# Contextual data that guards need but that isn't part of the state
# machine itself (e.g. "is this application part of a group?").


@dataclass(frozen=True, slots=True)
class TransitionContext:
    actor_user_account_id: int | None = None
    # Whether the application is part of an active group registration
    # with other active members. Used by the APPROVE guard: per-person
    # approval of an active group member is illegal; only the group
    # action may promote them (and it passes False here).
    is_part_of_active_group: bool = False
    # Whether a submission row (applicant details) exists. APPROVE
    # requires one: there is nothing to promote without it.
    has_submission: bool = True


# ── Public API ─────────────────────────────────────────────────────


def application_transition(
    state: ApplicationState,
    action: ApplicationAction,
    *,
    context: TransitionContext | None = None,
) -> TransitionResult:
    """Compute the result of applying *action* to *state*.

    Raises ``IllegalTransition`` if the transition is not allowed.
    """
    ctx = context or TransitionContext()

    # Deletion is reserved for records that have not entered an operational
    # lifecycle. The service adds the profile/submission guard.
    if action in _DELETE_ACTIONS and state == ApplicationState.NEW:
        return TransitionResult(
            new_state=state,
            event=DomainEventRecord(
                event_type="application_deleted",
                actor_user_account_id=ctx.actor_user_account_id,
                subject_type="application",
                subject_id=0,  # caller fills this in
                payload={"previous_state": state.value},
            ),
        )

    # Guards: per-person promotion of active group members is illegal,
    # and promotion requires applicant details to create the volunteer.
    if action == ApplicationAction.PROMOTE:
        if ctx.is_part_of_active_group:
            raise IllegalTransition(
                "Cannot approve an individual application that is part of "
                "an active group registration. Use group approval instead."
            )
        if not ctx.has_submission:
            raise IllegalTransition(
                "Cannot approve an application without submitted details."
            )

    # Standard transitions.
    new_state = _TRANSITIONS.get((state, action))
    if new_state is None:
        raise IllegalTransition(
            f"Cannot apply action '{action.value}' to state '{state.value}'."
        )

    effects: tuple[Effect, ...] = ()
    event: DomainEventRecord | None = None

    if action == ApplicationAction.SUBMIT_PROFILE:
        event = DomainEventRecord(
            # A promoted applicant re-submitting is completing their
            # volunteer profile, not re-applying.
            event_type=(
                "profile_completed"
                if state in (ApplicationState.TRIAL, ApplicationState.VOLUNTEER)
                else "application_submitted"
            ),
            actor_user_account_id=ctx.actor_user_account_id,
            subject_type="application",
            subject_id=0,
            payload={"previous_state": state.value},
        )

    elif action == ApplicationAction.CONTACT:
        event = DomainEventRecord(
            event_type="application_contacted",
            actor_user_account_id=ctx.actor_user_account_id,
            subject_type="application",
            subject_id=0,
            payload={"previous_state": state.value},
        )

    elif action == ApplicationAction.START_TRIAL:
        event = DomainEventRecord(
            event_type="trial_started",
            actor_user_account_id=ctx.actor_user_account_id,
            subject_type="application",
            subject_id=0,
            payload={"previous_state": state.value},
        )

    elif action == ApplicationAction.PROMOTE:
        effects = (SendApprovalEmail(
            registration_id=0,  # caller fills in
            volunteer_id=0,     # caller fills in
        ),)
        event = DomainEventRecord(
            event_type="application_approved",
            actor_user_account_id=ctx.actor_user_account_id,
            subject_type="application",
            subject_id=0,
            payload={"previous_state": state.value},
        )

    elif action == ApplicationAction.REJECT:
        event = DomainEventRecord(
            event_type="application_rejected",
            actor_user_account_id=ctx.actor_user_account_id,
            subject_type="application",
            subject_id=0,
            payload={"previous_state": state.value},
        )

    elif action == ApplicationAction.REOPEN:
        event = DomainEventRecord(
            event_type="application_reopened",
            actor_user_account_id=ctx.actor_user_account_id,
            subject_type="application",
            subject_id=0,
            payload={"previous_state": state.value},
        )

    elif action == ApplicationAction.RESTORE_VOLUNTEER:
        event = DomainEventRecord(
            event_type="application_volunteer_restored",
            actor_user_account_id=ctx.actor_user_account_id,
            subject_type="application",
            subject_id=0,
            payload={"previous_state": state.value},
        )

    elif action == ApplicationAction.RESEND_INVITATION:
        event = DomainEventRecord(
            event_type="invitation_resent",
            actor_user_account_id=ctx.actor_user_account_id,
            subject_type="application",
            subject_id=0,
            payload={"previous_state": state.value},
        )

    return TransitionResult(new_state=new_state, effects=effects, event=event)


def membership_transition(
    state: MembershipState,
    action: ApplicationAction,
    *,
    context: TransitionContext | None = None,
) -> TransitionResult:
    """Compute the result of applying *action* to a membership *state*."""
    ctx = context or TransitionContext()

    new_state = _MEMBERSHIP_TRANSITIONS.get((state, action))
    if new_state is None:
        raise IllegalTransition(
            f"Cannot apply action '{action.value}' to membership state '{state.value}'."
        )

    event = DomainEventRecord(
        event_type="group_member_dropped",
        actor_user_account_id=ctx.actor_user_account_id,
        subject_type="group_member",
        subject_id=0,
        payload={"previous_state": state.value},
    )

    return TransitionResult(new_state=new_state, event=event)
