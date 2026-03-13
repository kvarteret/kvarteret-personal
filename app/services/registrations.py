from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from secrets import token_urlsafe
from typing import Protocol


class RegistrationError(RuntimeError):
    pass


class RegistrationNotFoundError(RegistrationError):
    pass


class RegistrationConflictError(RegistrationError):
    pass


@dataclass(slots=True)
class RegistrationInvite:
    registration_id: int
    token: str
    email: str
    created_at: datetime


@dataclass(slots=True)
class PendingRegistrationItem:
    registration_id: int
    token: str
    email: str
    created_at: datetime
    submitted: bool
    first_name: str | None
    last_name: str | None
    phone: str | None


@dataclass(slots=True)
class PendingRegistrationDetail:
    registration_id: int
    token: str
    email: str
    created_at: datetime
    submitted: bool
    pending_person_id: int | None
    first_name: str | None
    last_name: str | None
    phone: str | None
    birth_date: date | None
    gender: str | None
    address: str | None
    postal_code: str | None
    employment_status: int | None


@dataclass(slots=True)
class RegistrationSubmissionInput:
    first_name: str | None
    last_name: str
    phone: str | None
    birth_date: date | None
    gender: str
    address: str | None
    postal_code: str | None
    employment_status: int | None


class RegistrationsServiceProtocol(Protocol):
    async def create_invitation(self, email: str) -> RegistrationInvite: ...
    async def list_pending(self) -> list[PendingRegistrationItem]: ...
    async def get_pending_detail(self, registration_id: int) -> PendingRegistrationDetail | None: ...
    async def get_invitation_by_token(self, token: str) -> PendingRegistrationDetail | None: ...
    async def submit_registration(self, token: str, submission: RegistrationSubmissionInput) -> PendingRegistrationDetail: ...
    async def approve_registration(self, registration_id: int) -> int: ...
    async def reject_registration(self, registration_id: int) -> None: ...


class RegistrationsRepositoryProtocol(Protocol):
    async def create_invitation(self, *, email: str, token: str) -> RegistrationInvite: ...
    async def list_pending(self) -> list[PendingRegistrationItem]: ...
    async def get_pending_detail(self, registration_id: int) -> PendingRegistrationDetail | None: ...
    async def get_invitation_by_token(self, token: str) -> PendingRegistrationDetail | None: ...
    async def save_submission(
        self,
        *,
        registration_id: int,
        email: str,
        submission: RegistrationSubmissionInput,
    ) -> None: ...
    async def find_person_id_by_email(self, email: str) -> int | None: ...
    async def approve_registration(self, registration: PendingRegistrationDetail) -> int: ...
    async def reject_registration(self, registration_id: int) -> None: ...


class RegistrationsService:
    def __init__(self, repository: RegistrationsRepositoryProtocol) -> None:
        self.repository = repository

    async def create_invitation(self, email: str) -> RegistrationInvite:
        normalized_email = email.strip().lower()
        if not normalized_email:
            raise RegistrationConflictError("An email address is required.")
        token = token_urlsafe(24)
        return await self.repository.create_invitation(email=normalized_email, token=token)

    async def list_pending(self) -> list[PendingRegistrationItem]:
        return await self.repository.list_pending()

    async def get_pending_detail(self, registration_id: int) -> PendingRegistrationDetail | None:
        return await self.repository.get_pending_detail(registration_id)

    async def get_invitation_by_token(self, token: str) -> PendingRegistrationDetail | None:
        return await self.repository.get_invitation_by_token(token)

    async def submit_registration(self, token: str, submission: RegistrationSubmissionInput) -> PendingRegistrationDetail:
        existing = await self.get_invitation_by_token(token)
        if existing is None:
            raise RegistrationNotFoundError("Registration token was not found.")

        await self.repository.save_submission(
            registration_id=existing.registration_id,
            email=existing.email,
            submission=submission,
        )
        detail = await self.get_invitation_by_token(token)
        if detail is None:
            raise RegistrationNotFoundError("Registration token was not found.")
        return detail

    async def approve_registration(self, registration_id: int) -> int:
        detail = await self.get_pending_detail(registration_id)
        if detail is None:
            raise RegistrationNotFoundError("Registration was not found.")
        if detail.pending_person_id is None:
            raise RegistrationConflictError("Registration has not been submitted yet.")
        duplicate_person = await self.repository.find_person_id_by_email(detail.email)
        if duplicate_person is not None:
            raise RegistrationConflictError("A person with this email already exists.")
        return await self.repository.approve_registration(detail)

    async def reject_registration(self, registration_id: int) -> None:
        detail = await self.get_pending_detail(registration_id)
        if detail is None:
            raise RegistrationNotFoundError("Registration was not found.")
        await self.repository.reject_registration(registration_id)
