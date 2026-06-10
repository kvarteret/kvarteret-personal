"""Exhaustive test matrix for the volunteer application state machine."""

import pytest

from app.domain.volunteer_applications.state_machine import (
    ApplicationAction,
    ApplicationState,
    IllegalTransition,
    MembershipState,
    SendApplicantEmail,
    SendApprovalEmail,
    SendRejectionEmail,
    TransitionContext,
    application_transition,
    membership_transition,
)

# ── Application state machine ─────────────────────────────────────

# Every state/action pair must be either legal or raise IllegalTransition.
APPLICATION_TEST_CASES = [
    # (state, action, expected_new_state_or_None)
    (ApplicationState.PROSPECT, ApplicationAction.SUBMIT_PROFILE, ApplicationState.SUBMITTED),
    (ApplicationState.PROSPECT, ApplicationAction.RESEND_INVITATION, None),
    (ApplicationState.PROSPECT, ApplicationAction.MARK_TRIAL_SHIFT, None),
    (ApplicationState.PROSPECT, ApplicationAction.APPROVE, None),
    (ApplicationState.PROSPECT, ApplicationAction.REJECT, None),
    (ApplicationState.PROSPECT, ApplicationAction.DELETE, ApplicationState.PROSPECT),  # removed
    (ApplicationState.PROSPECT, ApplicationAction.DROP_MEMBER, None),

    (ApplicationState.INVITED, ApplicationAction.SUBMIT_PROFILE, ApplicationState.SUBMITTED),
    (ApplicationState.INVITED, ApplicationAction.RESEND_INVITATION, ApplicationState.INVITED),
    (ApplicationState.INVITED, ApplicationAction.MARK_TRIAL_SHIFT, None),
    (ApplicationState.INVITED, ApplicationAction.APPROVE, None),
    (ApplicationState.INVITED, ApplicationAction.REJECT, None),
    (ApplicationState.INVITED, ApplicationAction.DELETE, ApplicationState.INVITED),  # removed
    (ApplicationState.INVITED, ApplicationAction.DROP_MEMBER, None),

    (ApplicationState.SUBMITTED, ApplicationAction.SUBMIT_PROFILE, None),
    (ApplicationState.SUBMITTED, ApplicationAction.RESEND_INVITATION, None),
    (ApplicationState.SUBMITTED, ApplicationAction.MARK_TRIAL_SHIFT, ApplicationState.SUBMITTED),
    (ApplicationState.SUBMITTED, ApplicationAction.APPROVE, ApplicationState.PROMOTED),
    (ApplicationState.SUBMITTED, ApplicationAction.REJECT, ApplicationState.REJECTED),
    (ApplicationState.SUBMITTED, ApplicationAction.DELETE, ApplicationState.SUBMITTED),  # removed
    (ApplicationState.SUBMITTED, ApplicationAction.DROP_MEMBER, None),

    (ApplicationState.PROMOTED, ApplicationAction.SUBMIT_PROFILE, None),
    (ApplicationState.PROMOTED, ApplicationAction.RESEND_INVITATION, None),
    (ApplicationState.PROMOTED, ApplicationAction.MARK_TRIAL_SHIFT, None),
    (ApplicationState.PROMOTED, ApplicationAction.APPROVE, None),
    (ApplicationState.PROMOTED, ApplicationAction.REJECT, None),
    (ApplicationState.PROMOTED, ApplicationAction.DELETE, None),
    (ApplicationState.PROMOTED, ApplicationAction.DROP_MEMBER, None),

    (ApplicationState.REJECTED, ApplicationAction.SUBMIT_PROFILE, None),
    (ApplicationState.REJECTED, ApplicationAction.RESEND_INVITATION, None),
    (ApplicationState.REJECTED, ApplicationAction.MARK_TRIAL_SHIFT, None),
    (ApplicationState.REJECTED, ApplicationAction.APPROVE, None),
    (ApplicationState.REJECTED, ApplicationAction.REJECT, None),
    (ApplicationState.REJECTED, ApplicationAction.DELETE, ApplicationState.REJECTED),  # removed
    (ApplicationState.REJECTED, ApplicationAction.DROP_MEMBER, None),
]

MEMBERSHIP_TEST_CASES = [
    # (state, action, expected_new_state_or_None)
    (MembershipState.ACTIVE, ApplicationAction.DROP_MEMBER, MembershipState.DROPPED),
    (MembershipState.ACTIVE, ApplicationAction.SUBMIT_PROFILE, None),
    (MembershipState.DROPPED, ApplicationAction.DROP_MEMBER, None),
    (MembershipState.DROPPED, ApplicationAction.SUBMIT_PROFILE, None),
]


@pytest.mark.parametrize("state,action,expected", APPLICATION_TEST_CASES)
def test_application_transition_matrix(state, action, expected):
    """Every state/action pair is exhaustively covered."""
    if expected is None:
        with pytest.raises(IllegalTransition):
            application_transition(state, action)
    else:
        result = application_transition(state, action)
        assert result.new_state == expected


@pytest.mark.parametrize("state,action,expected", MEMBERSHIP_TEST_CASES)
def test_membership_transition_matrix(state, action, expected):
    if expected is None:
        with pytest.raises(IllegalTransition):
            membership_transition(state, action)
    else:
        result = membership_transition(state, action)
        assert result.new_state == expected


# ── Side-effect tests ─────────────────────────────────────────────


def test_submit_profile_emits_applicant_email_effect():
    result = application_transition(
        ApplicationState.PROSPECT, ApplicationAction.SUBMIT_PROFILE,
    )
    assert len(result.effects) == 1
    assert isinstance(result.effects[0], SendApplicantEmail)
    assert result.event is not None
    assert result.event.event_type == "application_submitted"


def test_approve_emits_approval_email_effect():
    result = application_transition(
        ApplicationState.SUBMITTED, ApplicationAction.APPROVE,
    )
    assert len(result.effects) == 1
    assert isinstance(result.effects[0], SendApprovalEmail)
    assert result.event is not None
    assert result.event.event_type == "application_approved"


def test_reject_emits_rejection_email_effect():
    result = application_transition(
        ApplicationState.SUBMITTED, ApplicationAction.REJECT,
    )
    assert len(result.effects) == 1
    assert isinstance(result.effects[0], SendRejectionEmail)
    assert result.event is not None
    assert result.event.event_type == "application_rejected"


def test_mark_trial_shift_emits_audit_event():
    result = application_transition(
        ApplicationState.SUBMITTED, ApplicationAction.MARK_TRIAL_SHIFT,
    )
    assert len(result.effects) == 0
    assert result.event is not None
    assert result.event.event_type == "trial_shift_marked"


def test_resend_invitation_is_noop():
    result = application_transition(
        ApplicationState.INVITED, ApplicationAction.RESEND_INVITATION,
    )
    assert result.new_state == ApplicationState.INVITED
    assert len(result.effects) == 0


# ── Guard tests ───────────────────────────────────────────────────


def test_approve_blocked_for_active_group_member():
    with pytest.raises(IllegalTransition, match="group approval"):
        application_transition(
            ApplicationState.SUBMITTED,
            ApplicationAction.APPROVE,
            context=TransitionContext(is_part_of_active_group=True),
        )


def test_approve_allowed_for_solo_applicant():
    result = application_transition(
        ApplicationState.SUBMITTED,
        ApplicationAction.APPROVE,
        context=TransitionContext(is_part_of_active_group=False),
    )
    assert result.new_state == ApplicationState.PROMOTED


def test_delete_allowed_pre_promotion():
    for state in (
        ApplicationState.PROSPECT,
        ApplicationState.INVITED,
        ApplicationState.SUBMITTED,
        ApplicationState.REJECTED,
    ):
        result = application_transition(state, ApplicationAction.DELETE)
        assert result.event is not None
        assert result.event.event_type == "application_deleted"


def test_delete_blocked_after_promotion():
    with pytest.raises(IllegalTransition):
        application_transition(
            ApplicationState.PROMOTED, ApplicationAction.DELETE,
        )
