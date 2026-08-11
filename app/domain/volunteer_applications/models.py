"""Models, errors, and protocols for the volunteer application module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from math import ceil
from typing import Protocol

from app.domain.volunteer_applications.state_machine import (
    ApplicationState,
    MembershipState,
)


def build_full_name(first_name: str | None, last_name: str) -> str:
    return " ".join(part for part in [first_name or "", last_name] if part.strip()).strip() or last_name


class VolunteerApplicationsError(RuntimeError):
    pass


class VolunteerApplicationNotFoundError(VolunteerApplicationsError):
    pass


class VolunteerApplicationConflictError(VolunteerApplicationsError):
    pass


class VolunteerApplicationValidationError(VolunteerApplicationsError):
    pass


class VolunteerAlreadyExistsError(VolunteerApplicationConflictError):
    def __init__(self, volunteer_id: int, email: str) -> None:
        self.volunteer_id = volunteer_id
        self.email = email
        super().__init__(f"A volunteer with this email already exists (id={volunteer_id}).")


class VolunteerApplicationFieldValidationError(VolunteerApplicationValidationError):
    def __init__(self, message: str, field_errors: dict[str, object]) -> None:
        self.field_errors = field_errors
        super().__init__(message)


class VolunteerApplicationFieldConflictError(VolunteerApplicationConflictError):
    def __init__(self, message: str, field_errors: dict[str, object]) -> None:
        self.field_errors = field_errors
        super().__init__(message)


class ActiveVolunteerRegistrationExistsError(VolunteerApplicationConflictError):
    def __init__(self, registration_id: int, email: str) -> None:
        self.registration_id = registration_id
        self.email = email
        super().__init__(f"An active volunteer application with this email already exists (id={registration_id}).")


@dataclass(slots=True)
class VolunteerApplicationInvite:
    registration_id: int
    token: str
    email: str
    created_at: datetime
    initial_group_id: int | None = None
    initial_group_name: str | None = None
    initial_role_id: int | None = None
    initial_role_name: str | None = None


@dataclass(slots=True)
class VolunteerApplicationFriendInvite:
    registration_id: int
    token: str
    email: str
    inviter_name: str
    first_choice_group_name: str


@dataclass(slots=True)
class PublicProspectRegistrationResult:
    detail: "VolunteerApplicationDetail"
    friend_invites: list[VolunteerApplicationFriendInvite]


@dataclass(slots=True)
class VolunteerApplicationGroupMember:
    group_id: int
    registration_id: int | None
    email: str
    role: str
    status: str
    submitted: bool
    pending_volunteer_id: int | None
    first_name: str | None
    last_name: str | None
    trial_shift_attended: bool
    promoted_volunteer_id: int | None
    application_status: str | None = None
    dropped_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self.status == MembershipState.ACTIVE

    @property
    def display_name(self) -> str:
        return build_full_name(self.first_name, self.last_name or "") or self.email


@dataclass(slots=True)
class VolunteerApplicationListItem:
    registration_id: int
    token: str
    email: str
    created_at: datetime
    submitted: bool
    source: str
    status: str
    pending_volunteer_id: int | None
    first_name: str | None
    last_name: str | None
    phone: str | None
    study_institution: str | None
    background_details: str | None
    initial_group_id: int | None = None
    initial_group_name: str | None = None
    initial_role_id: int | None = None
    initial_role_name: str | None = None
    first_choice_group_id: int | None = None
    first_choice_group_name: str | None = None
    second_choice_group_id: int | None = None
    second_choice_group_name: str | None = None
    trial_shift_attended: bool = False
    promoted_volunteer_id: int | None = None
    promoted_at: datetime | None = None
    group_id: int | None = None
    group_role: str | None = None
    group_status: str | None = None
    group_members: list[VolunteerApplicationGroupMember] | None = None
    trial_started_at: datetime | None = None
    trial_ends_at: datetime | None = None

    @property
    def status_label(self) -> str:
        return application_status_label(self.status)

    @property
    def trial_days_remaining(self) -> int | None:
        return trial_days_remaining(self.trial_ends_at)

    @property
    def trial_expired(self) -> bool:
        return self.trial_ends_at is not None and trial_days_remaining(self.trial_ends_at) == 0


@dataclass(slots=True)
class VolunteerApplicationDetail:
    registration_id: int
    token: str
    email: str
    created_at: datetime
    submitted: bool
    source: str
    status: str
    pending_volunteer_id: int | None
    first_name: str | None
    last_name: str | None
    phone: str | None
    birth_date: date | None
    gender: str | None
    address: str | None
    postal_code: str | None
    photo_sha1: str | None
    photo_filetype: str | None
    photo_url: str | None
    study_institution: str | None
    background_details: str | None
    initial_group_id: int | None = None
    initial_group_name: str | None = None
    initial_role_id: int | None = None
    initial_role_name: str | None = None
    first_choice_group_id: int | None = None
    first_choice_group_name: str | None = None
    second_choice_group_id: int | None = None
    second_choice_group_name: str | None = None
    trial_shift_attended: bool = False
    trial_shift_marked_at: datetime | None = None
    promoted_volunteer_id: int | None = None
    promoted_at: datetime | None = None
    group_id: int | None = None
    group_role: str | None = None
    group_status: str | None = None
    group_members: list[VolunteerApplicationGroupMember] | None = None
    trial_started_at: datetime | None = None
    trial_ends_at: datetime | None = None
    status_history: list["VolunteerApplicationStatusEvent"] | None = None
    origin_trace_id: str | None = None

    @property
    def is_part_of_active_group(self) -> bool:
        """True when this application belongs to an active group with
        other active members — per-person approval is then illegal."""
        if not self.group_id or self.group_status != MembershipState.ACTIVE:
            return False
        return any(
            member.active and member.registration_id != self.registration_id for member in self.group_members or []
        )

    @property
    def status_label(self) -> str:
        return application_status_label(self.status)

    @property
    def trial_days_remaining(self) -> int | None:
        return trial_days_remaining(self.trial_ends_at)

    @property
    def trial_active(self) -> bool:
        return self.status == "trial" and (self.trial_days_remaining or 0) > 0

    @property
    def trial_expired(self) -> bool:
        return self.status == "trial" and self.trial_ends_at is not None and not self.trial_active

    @property
    def profile_complete(self) -> bool:
        return self.submitted and self.photo_sha1 is not None and self.photo_filetype is not None


@dataclass(frozen=True, slots=True)
class VolunteerApplicationStatusEvent:
    event_type: str
    status: str
    actor_display_name: str | None
    actor_user_account_id: int | None
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class TrialApplicantCardSnapshot:
    application_id: int
    first_name: str
    last_name: str
    birth_date: date | None
    created_at: datetime
    trial_ends_at: datetime
    photo_path: str
    group_name: str
    role_name: str
    discount_level: int | None


@dataclass(slots=True)
class RecentVolunteerRegistrationItem:
    volunteer_id: int
    first_name: str | None
    last_name: str
    full_name: str
    email: str | None
    phone: str | None
    created_at: datetime
    latest_group_name: str | None
    latest_role_name: str | None
    latest_semester_code: int | None = None
    latest_semester_label: str | None = None
    photo_url: str | None = None
    registration_id: int | None = None
    group_id: int | None = None
    group_role: str | None = None
    group_status: str | None = None
    group_members: list[RecentVolunteerRegistrationItem] | None = None
    renders_group: bool = False


@dataclass(slots=True)
class RecentVolunteerRegistrationPage:
    items: list[RecentVolunteerRegistrationItem]
    limit: int
    cursor: str | None
    next_cursor: str | None


@dataclass(slots=True)
class VolunteerApplicationSubmissionInput:
    first_name: str | None
    last_name: str
    phone: str | None
    birth_date: date | None
    gender: str
    address: str | None
    postal_code: str | None


@dataclass(slots=True)
class PublicProspectRegistrationInput:
    full_name: str
    email: str
    phone: str
    study_institution: str
    background_details: str | None
    first_choice_group_slug: str
    second_choice_group_slug: str | None
    friend_emails: list[str] | None = None


@dataclass(frozen=True, slots=True)
class PublicProspectGroup:
    group_id: int
    slug: str
    name: str


class VolunteerApplicationsServiceProtocol(Protocol):
    async def create_public_prospect_registration(
        self,
        registration: PublicProspectRegistrationInput,
        *,
        base_url: str | None = None,
    ) -> VolunteerApplicationDetail: ...
    async def create_volunteer_application_invitation(
        self,
        email: str,
        *,
        base_url: str | None = None,
        initial_group_id: int | None = None,
        initial_role_id: int | None = None,
    ) -> VolunteerApplicationInvite: ...
    async def list_volunteer_applications(
        self,
    ) -> list[VolunteerApplicationListItem]: ...
    async def list_recent_volunteer_registrations_page(
        self,
        limit: int = 20,
        cursor: str | None = None,
    ) -> RecentVolunteerRegistrationPage: ...
    async def count_pending_volunteer_applications(self) -> int: ...
    async def get_volunteer_application_detail(self, registration_id: int) -> VolunteerApplicationDetail | None: ...
    async def get_volunteer_application_by_token(self, token: str) -> VolunteerApplicationDetail | None: ...
    async def submit_volunteer_application(
        self,
        token: str,
        submission: VolunteerApplicationSubmissionInput,
        *,
        base_url: str | None = None,
        photo_filename: str | None = None,
        photo_content: bytes | None = None,
        photo_content_type: str | None = None,
    ) -> VolunteerApplicationDetail: ...
    async def mark_contacted(
        self, registration_id: int
    ) -> VolunteerApplicationDetail: ...
    async def start_trial(
        self, registration_id: int, *, base_url: str | None = None
    ) -> VolunteerApplicationDetail: ...
    async def reject_volunteer_application(
        self, registration_id: int
    ) -> VolunteerApplicationDetail: ...
    async def reopen_volunteer_application(
        self, registration_id: int
    ) -> VolunteerApplicationDetail: ...
    async def approve_volunteer_application(
        self,
        registration_id: int,
        *,
        accepted_group_id: int | None = None,
        base_url: str | None = None,
    ) -> int: ...
    async def delete_volunteer_application(self, registration_id: int) -> None: ...
    async def resend_volunteer_application_invitation(
        self,
        registration_id: int,
        *,
        base_url: str | None = None,
    ) -> VolunteerApplicationDetail: ...


class VolunteerCreatorProtocol(Protocol):
    """Port to the volunteers module: onboarding on approval.

    Satisfied by ``VolunteersService``; wired in ``app/runtime.py`` so
    the applications module never imports another module's service.
    """

    async def create_from_application(
        self,
        *,
        first_name: str | None,
        last_name: str,
        email: str | None,
        gender: str,
        birth_date: date | None,
        street_address: str | None,
        postal_code: str | None,
        phone: str | None,
        photo_sha1: str | None,
        photo_filetype: str | None,
        group_id: int,
        role_id: int | None,
        contract_signed: bool,
    ) -> int: ...


_APPLICATION_STATUS_LABELS = {
    "new": "Ny",
    "contacted": "Kontaktet",
    "trial": "På prøve",
    "volunteer": "Frivillig",
    "not_volunteer": "Ikke frivillig",
}


def application_status_label(status: str) -> str:
    return _APPLICATION_STATUS_LABELS.get(status, status)


def trial_days_remaining(trial_ends_at: datetime | None, *, now: datetime | None = None) -> int | None:
    if trial_ends_at is None:
        return None
    current = now or datetime.now(UTC)
    end = trial_ends_at if trial_ends_at.tzinfo is not None else trial_ends_at.replace(tzinfo=UTC)
    return max(0, ceil((end - current).total_seconds() / 86_400))


class VolunteerApplicationsRepositoryProtocol(Protocol):
    async def create_public_prospect_registration(
        self,
        *,
        token: str,
        email: str,
        first_name: str | None,
        last_name: str,
        phone: str | None,
        study_institution: str | None,
        background_details: str | None,
        first_choice_label: str,
        second_choice_label: str | None,
        initial_group_id: int | None,
        initial_role_id: int | None,
        first_choice_group_id: int,
        second_choice_group_id: int | None,
        friend_invites: list[tuple[str, str]] | None = None,
        inviter_name: str | None = None,
        first_choice_group_name: str | None = None,
        origin_trace_id: str | None = None,
    ) -> PublicProspectRegistrationResult: ...
    async def create_volunteer_application_invitation(
        self,
        *,
        email: str,
        token: str,
        initial_group_id: int | None = None,
        initial_role_id: int | None = None,
    ) -> VolunteerApplicationInvite: ...
    async def count_pending_volunteer_applications(self) -> int: ...
    async def get_volunteer_application_detail(self, registration_id: int) -> VolunteerApplicationDetail | None: ...
    async def get_volunteer_application_by_token(self, token: str) -> VolunteerApplicationDetail | None: ...
    async def find_public_prospect_groups_by_slugs(self, slugs: list[str]) -> dict[str, PublicProspectGroup]: ...
    async def find_public_prospect_role_id(self, *, group_id: int, role_name: str) -> int | None: ...
    async def save_submission(
        self,
        *,
        registration_id: int,
        email: str,
        submission: VolunteerApplicationSubmissionInput,
        photo_sha1: str | None,
        photo_filetype: str | None,
    ) -> None: ...
    async def set_application_status(
        self,
        registration_id: int,
        *,
        status: ApplicationState,
        start_trial: bool = False,
    ) -> None: ...
    async def find_active_trial_applicant_by_email(
        self, email: str
    ) -> TrialApplicantCardSnapshot | None: ...
    async def get_active_trial_applicant(
        self, application_id: int
    ) -> TrialApplicantCardSnapshot | None: ...
    async def find_volunteer_id_by_email(self, email: str) -> int | None: ...
    async def find_active_registration_id_by_email(self, email: str) -> int | None: ...
    async def list_group_members(
        self, group_id: int, *, include_dropped: bool = True
    ) -> list[VolunteerApplicationGroupMember]: ...
    async def drop_group_invitee(self, registration_id: int, *, dropped_by_user_id: int | None = None) -> None: ...
    async def role_matches_group(self, *, role_id: int, group_id: int) -> bool: ...
    async def mark_promoted(self, *, registration_id: int, volunteer_id: int, accepted_group_id: int) -> None: ...
    async def delete_volunteer_application(self, registration_id: int) -> None: ...
