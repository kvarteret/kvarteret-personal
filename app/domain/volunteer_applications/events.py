"""Domain events for the volunteer_applications bounded context.

These events are published by the VolunteerApplicationsService and consumed
by handlers registered on the SimpleEventBus in runtime.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ApplicationSubmitted:
    """Published when an applicant submits their application form."""

    registration_id: int
    first_name: str | None
    last_name: str | None
    email: str


@dataclass(slots=True)
class ApplicationApproved:
    """Published when an application is approved and a volunteer is created."""

    volunteer_id: int
    email: str
    token: str  # for profile completion email


@dataclass(slots=True)
class TrialShiftMarked:
    """Published when a trial shift attendance is recorded."""

    registration_id: int
    attended: bool
