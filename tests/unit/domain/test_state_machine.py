"""Exhaustive tests for the volunteer application state machine."""

import pytest

from app.domain.volunteer_applications.state_machine import (
    ApplicationAction,
    ApplicationState,
    IllegalTransition,
    MembershipState,
    SendApprovalEmail,
    TransitionContext,
    application_transition,
    membership_transition,
)


EXPECTED_APPLICATION_TRANSITIONS = {
    (ApplicationState.NEW, ApplicationAction.SUBMIT_PROFILE): ApplicationState.NEW,
    (ApplicationState.NEW, ApplicationAction.RESEND_INVITATION): ApplicationState.NEW,
    (ApplicationState.NEW, ApplicationAction.CONTACT): ApplicationState.CONTACTED,
    (ApplicationState.NEW, ApplicationAction.REJECT): ApplicationState.NOT_VOLUNTEER,
    (ApplicationState.NEW, ApplicationAction.DELETE): ApplicationState.NEW,
    (ApplicationState.CONTACTED, ApplicationAction.SUBMIT_PROFILE): ApplicationState.CONTACTED,
    (ApplicationState.CONTACTED, ApplicationAction.RESEND_INVITATION): ApplicationState.CONTACTED,
    (ApplicationState.CONTACTED, ApplicationAction.START_TRIAL): ApplicationState.TRIAL,
    (ApplicationState.CONTACTED, ApplicationAction.REJECT): ApplicationState.NOT_VOLUNTEER,
    (ApplicationState.TRIAL, ApplicationAction.SUBMIT_PROFILE): ApplicationState.TRIAL,
    (ApplicationState.TRIAL, ApplicationAction.PROMOTE): ApplicationState.VOLUNTEER,
    (ApplicationState.TRIAL, ApplicationAction.REJECT): ApplicationState.NOT_VOLUNTEER,
    (ApplicationState.VOLUNTEER, ApplicationAction.SUBMIT_PROFILE): ApplicationState.VOLUNTEER,
    (ApplicationState.VOLUNTEER, ApplicationAction.REJECT): ApplicationState.NOT_VOLUNTEER,
    (ApplicationState.NOT_VOLUNTEER, ApplicationAction.REOPEN): ApplicationState.CONTACTED,
    (ApplicationState.NOT_VOLUNTEER, ApplicationAction.RESTORE_VOLUNTEER): ApplicationState.VOLUNTEER,
}


@pytest.mark.parametrize(
    "state,action",
    [(state, action) for state in ApplicationState for action in ApplicationAction],
)
def test_application_transition_matrix(state, action):
    expected = EXPECTED_APPLICATION_TRANSITIONS.get((state, action))
    if expected is None:
        with pytest.raises(IllegalTransition):
            application_transition(state, action)
    else:
        assert application_transition(state, action).new_state == expected


@pytest.mark.parametrize(
    "state,action,expected",
    [
        (MembershipState.ACTIVE, ApplicationAction.DROP_MEMBER, MembershipState.DROPPED),
        (MembershipState.ACTIVE, ApplicationAction.SUBMIT_PROFILE, None),
        (MembershipState.DROPPED, ApplicationAction.DROP_MEMBER, None),
        (MembershipState.DROPPED, ApplicationAction.SUBMIT_PROFILE, None),
    ],
)
def test_membership_transition_matrix(state, action, expected):
    if expected is None:
        with pytest.raises(IllegalTransition):
            membership_transition(state, action)
    else:
        assert membership_transition(state, action).new_state == expected


def test_contact_and_trial_start_emit_audit_events():
    contacted = application_transition(ApplicationState.NEW, ApplicationAction.CONTACT)
    trial = application_transition(ApplicationState.CONTACTED, ApplicationAction.START_TRIAL)

    assert contacted.event is not None
    assert contacted.event.event_type == "application_contacted"
    assert trial.event is not None
    assert trial.event.event_type == "trial_started"


def test_trial_profile_submission_is_profile_completion():
    result = application_transition(ApplicationState.TRIAL, ApplicationAction.SUBMIT_PROFILE)

    assert result.new_state == ApplicationState.TRIAL
    assert result.event is not None
    assert result.event.event_type == "profile_completed"


def test_promote_emits_approval_effect():
    result = application_transition(ApplicationState.TRIAL, ApplicationAction.PROMOTE)

    assert isinstance(result.effects[0], SendApprovalEmail)
    assert result.event is not None
    assert result.event.event_type == "application_approved"


def test_promote_requires_submission():
    with pytest.raises(IllegalTransition, match="submitted details"):
        application_transition(
            ApplicationState.TRIAL,
            ApplicationAction.PROMOTE,
            context=TransitionContext(has_submission=False),
        )


def test_promote_blocked_for_active_group_member():
    with pytest.raises(IllegalTransition, match="group approval"):
        application_transition(
            ApplicationState.TRIAL,
            ApplicationAction.PROMOTE,
            context=TransitionContext(is_part_of_active_group=True),
        )


def test_terminal_decision_can_be_reconsidered():
    rejected = application_transition(ApplicationState.VOLUNTEER, ApplicationAction.REJECT)
    reopened = application_transition(rejected.new_state, ApplicationAction.REOPEN)

    assert rejected.new_state == ApplicationState.NOT_VOLUNTEER
    assert reopened.new_state == ApplicationState.CONTACTED
    assert application_transition(
        rejected.new_state, ApplicationAction.RESTORE_VOLUNTEER
    ).new_state == ApplicationState.VOLUNTEER
