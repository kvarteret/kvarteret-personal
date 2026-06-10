"""Pure, I/O-free volunteer application state machine.

Encodes the application lifecycle as explicit states, actions, and
transitions.  Every state/action pair is either legal (produces a
``TransitionResult``) or illegal (raises ``IllegalTransition``).

The state diagram (verified against production data and the live routes
on 2026-06-10; the public-signup flow approves prospects after a trial
shift, and the post-approval profile-completion email reuses the same
/apply/{token} link, so SUBMIT_PROFILE is legal from PROMOTED)::

    prospect  ──submit-profile────────►  submitted
    invited   ──submit-profile────────►  submitted
    submitted ──submit-profile────────►  submitted   (edits before approval)
    promoted  ──submit-profile────────►  promoted    (post-approval completion)
    invited   ──resend-invitation─────►  invited
    {prospect,invited,submitted} ──mark-trial-shift──► (unchanged)
    prospect  ──approve───────────────►  promoted    (requires submission row)
    submitted ──approve───────────────►  promoted
    submitted ──reject────────────────►  rejected
    {prospect,invited,submitted} ──delete──► (removed)

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
    PROSPECT = "prospect"
    INVITED = "invited"
    SUBMITTED = "submitted"
    PROMOTED = "promoted"
    REJECTED = "rejected"


class MembershipState(StrEnum):
    ACTIVE = "active"
    DROPPED = "dropped"


class ApplicationAction(StrEnum):
    SUBMIT_PROFILE = "submit_profile"
    RESEND_INVITATION = "resend_invitation"
    MARK_TRIAL_SHIFT = "mark_trial_shift"
    APPROVE = "approve"
    REJECT = "reject"
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
    (ApplicationState.PROSPECT, ApplicationAction.SUBMIT_PROFILE): ApplicationState.SUBMITTED,
    (ApplicationState.INVITED, ApplicationAction.SUBMIT_PROFILE): ApplicationState.SUBMITTED,
    (ApplicationState.SUBMITTED, ApplicationAction.SUBMIT_PROFILE): ApplicationState.SUBMITTED,
    (ApplicationState.PROMOTED, ApplicationAction.SUBMIT_PROFILE): ApplicationState.PROMOTED,
    (ApplicationState.INVITED, ApplicationAction.RESEND_INVITATION): ApplicationState.INVITED,
    (ApplicationState.PROSPECT, ApplicationAction.MARK_TRIAL_SHIFT): ApplicationState.PROSPECT,
    (ApplicationState.INVITED, ApplicationAction.MARK_TRIAL_SHIFT): ApplicationState.INVITED,
    (ApplicationState.SUBMITTED, ApplicationAction.MARK_TRIAL_SHIFT): ApplicationState.SUBMITTED,
    (ApplicationState.PROSPECT, ApplicationAction.APPROVE): ApplicationState.PROMOTED,
    (ApplicationState.SUBMITTED, ApplicationAction.APPROVE): ApplicationState.PROMOTED,
    (ApplicationState.SUBMITTED, ApplicationAction.REJECT): ApplicationState.REJECTED,
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

    # Deletion is allowed for any pre-promotion state.
    if action in _DELETE_ACTIONS and state != ApplicationState.PROMOTED:
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

    # Guards: per-person approval of active group members is illegal,
    # and approval requires applicant details to promote from.
    if action == ApplicationAction.APPROVE:
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
                if state == ApplicationState.PROMOTED
                else "application_submitted"
            ),
            actor_user_account_id=ctx.actor_user_account_id,
            subject_type="application",
            subject_id=0,
            payload={"previous_state": state.value},
        )

    elif action == ApplicationAction.APPROVE:
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

    elif action == ApplicationAction.MARK_TRIAL_SHIFT:
        event = DomainEventRecord(
            event_type="trial_shift_marked",
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
