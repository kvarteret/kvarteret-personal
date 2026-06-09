from __future__ import annotations

import logging
import re
from asyncio import to_thread
from dataclasses import dataclass
from datetime import date, datetime
from secrets import token_hex, token_urlsafe
from typing import Protocol

from app.cache import TTLCache
from app.config import Settings
from app.errors import NotConfiguredError
from app.infrastructure.email.applicant_templates import (
    ApplicantEmailTemplateRenderer,
    ApplicantEmailTemplateRendererProtocol,
)
from app.infrastructure.email.protocols import EmailSenderProtocol
from app.infrastructure.media.photo_processing import process_uploaded_photo
from app.infrastructure.contact.phone_numbers import normalize_phone_number, normalize_required_phone_number
from app.infrastructure.formatting.semester import format_semester_code
from app.infrastructure.storage.service import StorageService

_REGISTRATION_NOT_FOUND = "Registration was not found."


def _normalize_phone(phone: str) -> str:
    try:
        return normalize_required_phone_number(phone)
    except ValueError as exc:
        raise VolunteerApplicationValidationError(str(exc)) from exc


def _check_postal_code(postal_code: str | None) -> None:
    if postal_code is not None and not re.fullmatch(r"\d{4}", postal_code):
        raise VolunteerApplicationValidationError(
            "Postal code must be exactly 4 digits (e.g. 5011)."
        )

PUBLIC_PROSPECT_GROUPS = {
    "skjenkegruppen": "Skjenkegruppen",
    "kraft": "Kraftetaten",
    "vaktetaten": "Vaktetaten",
}

logger = logging.getLogger(__name__)


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
    dropped_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self.status == "active"

    @property
    def display_name(self) -> str:
        return _build_full_name(self.first_name, self.last_name or "") or self.email


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
    async def list_volunteer_applications(self) -> list[VolunteerApplicationListItem]: ...
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
    async def mark_trial_shift_attended(self, registration_id: int, *, attended: bool) -> VolunteerApplicationDetail: ...
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
        first_choice_group_id: int,
        second_choice_group_id: int | None,
        friend_invites: list[tuple[str, str]] | None = None,
        inviter_name: str | None = None,
        first_choice_group_name: str | None = None,
    ) -> PublicProspectRegistrationResult: ...
    async def create_volunteer_application_invitation(
        self,
        *,
        email: str,
        token: str,
        initial_group_id: int | None = None,
        initial_role_id: int | None = None,
    ) -> VolunteerApplicationInvite: ...
    async def list_volunteer_applications(self) -> list[VolunteerApplicationListItem]: ...
    async def list_recent_volunteer_registrations(self, *, limit: int, before_volunteer_id: int | None = None) -> list[dict]: ...
    async def list_recent_registration_group_members(self, group_id: int) -> list[dict]: ...
    async def count_pending_volunteer_applications(self) -> int: ...
    async def get_volunteer_application_detail(self, registration_id: int) -> VolunteerApplicationDetail | None: ...
    async def get_volunteer_application_by_token(self, token: str) -> VolunteerApplicationDetail | None: ...
    async def find_group_ids_by_names(self, names: list[str]) -> dict[str, int]: ...
    async def save_submission(
        self,
        *,
        registration_id: int,
        email: str,
        submission: VolunteerApplicationSubmissionInput,
        photo_sha1: str | None,
        photo_filetype: str | None,
    ) -> None: ...
    async def set_trial_shift_attended(self, registration_id: int, *, attended: bool) -> None: ...
    async def find_volunteer_id_by_email(self, email: str) -> int | None: ...
    async def find_active_registration_id_by_email(self, email: str) -> int | None: ...
    async def list_group_members(self, group_id: int, *, include_dropped: bool = True) -> list[VolunteerApplicationGroupMember]: ...
    async def drop_group_invitee(self, registration_id: int, *, dropped_by_user_id: int | None = None) -> None: ...
    async def approve_volunteer_application(
        self,
        registration: VolunteerApplicationDetail,
        *,
        accepted_group_id: int | None,
    ) -> int: ...
    async def delete_volunteer_application(self, registration_id: int) -> None: ...


class VolunteerApplicationsService:
    def __init__(
        self,
        settings: Settings,
        repository: VolunteerApplicationsRepositoryProtocol,
        email_sender: EmailSenderProtocol,
        applicant_email_renderer: ApplicantEmailTemplateRendererProtocol | None = None,
        storage_service: StorageService | None = None,
        pending_count_cache_ttl_seconds: int = 30,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.email_sender = email_sender
        self.applicant_email_renderer = applicant_email_renderer or ApplicantEmailTemplateRenderer()
        self.storage_service = storage_service
        self._pending_count_cache: TTLCache[str, int] = TTLCache(
            ttl_seconds=pending_count_cache_ttl_seconds,
            max_entries=1,
        )

    async def create_public_prospect_registration(
        self,
        registration: PublicProspectRegistrationInput,
        *,
        base_url: str | None = None,
    ) -> VolunteerApplicationDetail:
        normalized_email = registration.email.strip().lower()
        if not normalized_email:
            raise VolunteerApplicationValidationError("E-postadresse er påkrevd.")
        duplicate_volunteer = await self.repository.find_volunteer_id_by_email(normalized_email)
        if duplicate_volunteer is not None:
            raise VolunteerAlreadyExistsError(duplicate_volunteer, normalized_email)
        duplicate_registration = await self.repository.find_active_registration_id_by_email(normalized_email)
        if duplicate_registration is not None:
            raise ActiveVolunteerRegistrationExistsError(duplicate_registration, normalized_email)

        first_choice_slug = registration.first_choice_group_slug.strip().lower()
        second_choice_slug = (registration.second_choice_group_slug or "").strip().lower()
        if not first_choice_slug:
            raise VolunteerApplicationValidationError("Velg et førstevalg.")
        if second_choice_slug and first_choice_slug == second_choice_slug:
            raise VolunteerApplicationValidationError("Førstevalg og andrevalg må være ulike grupper.")

        known_choice_names = {
            slug: PUBLIC_PROSPECT_GROUPS[slug]
            for slug in [first_choice_slug, second_choice_slug]
            if slug
            if slug in PUBLIC_PROSPECT_GROUPS
        }
        expected_choice_count = 1 + (1 if second_choice_slug else 0)
        if len(known_choice_names) != expected_choice_count:
            raise VolunteerApplicationValidationError("Én eller flere valgte grupper støttes ikke i denne lanseringen.")

        group_ids_by_name = await self.repository.find_group_ids_by_names(list(known_choice_names.values()))
        if len(group_ids_by_name) != expected_choice_count:
            raise VolunteerApplicationConflictError("Én eller flere valgte grupper finnes ikke i personaldatabasen.")

        first_name, last_name = _split_full_name(registration.full_name)
        friend_emails = self._normalize_friend_emails(
            registration.friend_emails,
            inviter_email=normalized_email,
        )
        await self._assert_friend_emails_available(friend_emails)

        token = token_urlsafe(24)
        result = await self.repository.create_public_prospect_registration(
            token=token,
            email=normalized_email,
            first_name=first_name,
            last_name=last_name,
            phone=normalize_phone_number(registration.phone),
            study_institution=_normalize_optional_text(registration.study_institution),
            background_details=_normalize_optional_text(registration.background_details),
            first_choice_group_id=group_ids_by_name[known_choice_names[first_choice_slug]],
            second_choice_group_id=(
                group_ids_by_name[known_choice_names[second_choice_slug]]
                if second_choice_slug
                else None
            ),
            friend_invites=[(friend_email, token_urlsafe(24)) for friend_email in friend_emails],
            inviter_name=_build_full_name(first_name, last_name),
            first_choice_group_name=known_choice_names[first_choice_slug],
        )
        self._invalidate_pending_count_cache()
        for invite in result.friend_invites:
            try:
                await self._send_friend_invitation_email(
                    email=invite.email,
                    token=invite.token,
                    inviter_name=invite.inviter_name,
                    first_choice_group_name=invite.first_choice_group_name,
                    base_url=base_url,
                )
            except Exception:
                # The registration is already persisted so admins can resend the invitation.
                logger.exception("Failed to send group volunteer invitation email for registration %s", invite.registration_id)
                pass
        return result.detail

    async def create_volunteer_application_invitation(
        self,
        email: str,
        *,
        base_url: str | None = None,
        initial_group_id: int | None = None,
        initial_role_id: int | None = None,
    ) -> VolunteerApplicationInvite:
        normalized_email = email.strip().lower()
        if not normalized_email:
            raise VolunteerApplicationConflictError("An email address is required.")
        if (initial_group_id is None) != (initial_role_id is None):
            raise VolunteerApplicationConflictError("Choose both group and verv, or leave both empty.")
        duplicate_volunteer = await self.repository.find_volunteer_id_by_email(normalized_email)
        if duplicate_volunteer is not None:
            raise VolunteerAlreadyExistsError(duplicate_volunteer, normalized_email)
        token = token_urlsafe(24)
        invite = await self.repository.create_volunteer_application_invitation(
            email=normalized_email,
            token=token,
            initial_group_id=initial_group_id,
            initial_role_id=initial_role_id,
        )
        try:
            await self._send_invitation_email(email=invite.email, token=invite.token, base_url=base_url)
        except Exception:
            await self.repository.delete_volunteer_application(invite.registration_id)
            raise
        return invite

    async def list_volunteer_applications(self) -> list[VolunteerApplicationListItem]:
        return await self.repository.list_volunteer_applications()

    async def list_recent_volunteer_registrations_page(
        self,
        limit: int = 20,
        cursor: str | None = None,
    ) -> RecentVolunteerRegistrationPage:
        safe_limit = max(1, min(limit, 100))
        before_volunteer_id = _parse_recent_registration_cursor(cursor)
        rows = await self.repository.list_recent_volunteer_registrations(
            limit=safe_limit + 1,
            before_volunteer_id=before_volunteer_id,
        )
        has_more = len(rows) > safe_limit
        visible_rows = rows[:safe_limit]
        items = [self._map_recent_registration_row(row) for row in visible_rows]
        group_ids = sorted({item.group_id for item in items if item.group_id is not None})
        group_members_by_id: dict[int, list[RecentVolunteerRegistrationItem]] = {}
        for group_id in group_ids:
            group_members_by_id[group_id] = [
                self._map_recent_registration_row(row)
                for row in await self.repository.list_recent_registration_group_members(group_id)
            ]
        for item in items:
            if item.group_id is not None:
                item.group_members = group_members_by_id.get(item.group_id, [])
        seen_group_ids: set[int] = set()
        for item in items:
            if item.group_id is not None and item.group_id not in seen_group_ids:
                item.renders_group = True
                seen_group_ids.add(item.group_id)
        return RecentVolunteerRegistrationPage(
            items=items,
            limit=safe_limit,
            cursor=cursor,
            next_cursor=str(visible_rows[-1]["id"]) if has_more and visible_rows else None,
        )

    def _map_recent_registration_row(self, row: dict) -> RecentVolunteerRegistrationItem:
        return RecentVolunteerRegistrationItem(
            volunteer_id=row["id"],
            first_name=row["fornavn"],
            last_name=row["etternavn"],
            full_name=_build_full_name(row["fornavn"], row["etternavn"]),
            email=row["epost"],
            phone=row["telefon"],
            created_at=row["opprettet"],
            latest_group_name=row["latest_group_name"],
            latest_role_name=row["latest_role_name"],
            latest_semester_code=row["latest_semester_code"],
            latest_semester_label=(
                format_semester_code(row["latest_semester_code"])
                if row["latest_semester_code"] is not None
                else None
            ),
            photo_url=(
                self.repository.media_token_service.build_photo_media_url(
                    f"{row['photo_sha1']}.{row['photo_filetype']}"
                )
                if row.get("photo_sha1") and row.get("photo_filetype") and self.repository.media_token_service is not None
                else None
            ),
            registration_id=row.get("registration_id"),
            group_id=row.get("group_id"),
            group_role=row.get("group_role"),
            group_status=row.get("group_status"),
        )

    async def count_pending_volunteer_applications(self) -> int:
        cached_count = self._pending_count_cache.get("pending-count")
        if cached_count is not None:
            return cached_count
        pending_count = await self.repository.count_pending_volunteer_applications()
        self._pending_count_cache.set("pending-count", pending_count)
        return pending_count

    async def get_volunteer_application_detail(self, registration_id: int) -> VolunteerApplicationDetail | None:
        return await self.repository.get_volunteer_application_detail(registration_id)

    async def get_volunteer_application_by_token(self, token: str) -> VolunteerApplicationDetail | None:
        return await self.repository.get_volunteer_application_by_token(token)

    async def submit_volunteer_application(
        self,
        token: str,
        submission: VolunteerApplicationSubmissionInput,
        *,
        base_url: str | None = None,
        photo_filename: str | None = None,
        photo_content: bytes | None = None,
        photo_content_type: str | None = None,
    ) -> VolunteerApplicationDetail:
        existing = await self.get_volunteer_application_by_token(token)
        if existing is None:
            raise VolunteerApplicationNotFoundError("Registration token was not found.")

        submission.phone = _normalize_phone(submission.phone)
        _check_postal_code(submission.postal_code)

        # --- Photo handling ---
        has_existing_photo = existing.photo_sha1 is not None
        has_new_photo = bool(photo_filename and photo_content)
        missing_required_photo = not has_existing_photo and not has_new_photo
        if missing_required_photo:
            raise VolunteerApplicationValidationError("Profilbilde er påkrevd.")

        photo_sha1 = existing.photo_sha1
        photo_filetype = existing.photo_filetype
        old_storage_path = _build_photo_storage_path(existing.photo_sha1, existing.photo_filetype)
        new_storage_path = old_storage_path
        uploaded_new_photo = False
        storage_service: StorageService | None = None

        if has_new_photo:
            photo_sha1, photo_filetype, new_storage_path, storage_service = await self._upload_new_photo(
                photo_filename, photo_content
            )
            assert new_storage_path is not None
            uploaded_new_photo = True

        # --- Save and cleanup ---
        await self._save_and_cleanup_photos(
            existing=existing,
            submission=submission,
            photo_sha1=photo_sha1,
            photo_filetype=photo_filetype,
            old_storage_path=old_storage_path,
            new_storage_path=new_storage_path,
            uploaded_new_photo=uploaded_new_photo,
            storage_service=storage_service,
        )

        detail = await self.get_volunteer_application_by_token(token)
        if detail is None:
            raise VolunteerApplicationNotFoundError("Registration token was not found.")
        return detail

    async def _upload_new_photo(
        self, photo_filename: str, photo_content: bytes
    ) -> tuple[str, str, str, StorageService]:
        safe_filename = _sanitize_filename(photo_filename)
        extension = _normalize_extension(safe_filename)
        if extension not in {"jpg", "jpeg", "png", "webp"}:
            raise VolunteerApplicationConflictError(
                "Photos must be jpg, jpeg, png, or webp."
            )
        storage_service = self._require_storage_service()
        photo_sha1 = token_hex(20)
        processed = process_uploaded_photo(
            photo_content,
            max_upload_bytes=self.settings.photo_upload_max_bytes,
            max_dimension=self.settings.photo_max_dimension,
        )
        new_path = _build_photo_storage_path(photo_sha1, processed.extension)
        await to_thread(
            storage_service.upload_photo,
            new_path,
            processed.content,
            processed.content_type,
        )
        return photo_sha1, processed.extension, new_path, storage_service

    async def _save_and_cleanup_photos(
        self,
        *,
        existing: VolunteerApplicationDetail,
        submission: VolunteerApplicationSubmissionInput,
        photo_sha1: str | None,
        photo_filetype: str | None,
        old_storage_path: str | None,
        new_storage_path: str | None,
        uploaded_new_photo: bool,
        storage_service: StorageService | None,
    ) -> None:
        try:
            await self.repository.save_submission(
                registration_id=existing.registration_id,
                email=existing.email,
                submission=submission,
                photo_sha1=photo_sha1,
                photo_filetype=photo_filetype,
            )
        except Exception:
            should_rollback = (
                uploaded_new_photo
                and storage_service is not None
                and new_storage_path is not None
                and new_storage_path != old_storage_path
            )
            if should_rollback:
                try:
                    await to_thread(
                        storage_service.remove_photo, new_storage_path
                    )
                except Exception:
                    pass
            raise

        self._invalidate_pending_count_cache()

        should_remove_old = (
            uploaded_new_photo
            and old_storage_path is not None
            and old_storage_path != new_storage_path
        )
        if should_remove_old:
            try:
                await to_thread(
                    self._require_storage_service().remove_photo,
                    old_storage_path,
                )
            except Exception:
                pass

    async def mark_trial_shift_attended(
        self,
        registration_id: int,
        *,
        attended: bool,
    ) -> VolunteerApplicationDetail:
        detail = await self.get_volunteer_application_detail(registration_id)
        if detail is None:
            raise VolunteerApplicationNotFoundError(_REGISTRATION_NOT_FOUND)
        await self.repository.set_trial_shift_attended(registration_id, attended=attended)
        refreshed = await self.get_volunteer_application_detail(registration_id)
        if refreshed is None:
            raise VolunteerApplicationNotFoundError(_REGISTRATION_NOT_FOUND)
        return refreshed

    async def approve_volunteer_application(
        self,
        registration_id: int,
        *,
        accepted_group_id: int | None = None,
        base_url: str | None = None,
    ) -> int:
        detail = await self.get_volunteer_application_detail(registration_id)
        if detail is None:
            raise VolunteerApplicationNotFoundError(_REGISTRATION_NOT_FOUND)
        if detail.pending_volunteer_id is None:
            raise VolunteerApplicationConflictError("Registration is missing prospect details.")
        if detail.promoted_volunteer_id is not None:
            raise VolunteerApplicationConflictError("Registration has already been promoted.")
        self._ensure_group_members_ready_for_promotion(detail)
        duplicate_volunteer = await self.repository.find_volunteer_id_by_email(detail.email)
        if duplicate_volunteer is not None:
            raise VolunteerAlreadyExistsError(duplicate_volunteer, detail.email)
        resolved_group_id = accepted_group_id or detail.initial_group_id or detail.first_choice_group_id
        allowed_group_ids = {
            group_id
            for group_id in [detail.initial_group_id, detail.first_choice_group_id, detail.second_choice_group_id]
            if group_id is not None
        }
        if resolved_group_id is None:
            raise VolunteerApplicationConflictError("Choose a group before promoting this prospect.")
        if allowed_group_ids and resolved_group_id not in allowed_group_ids:
            raise VolunteerApplicationConflictError("The chosen group is not one of the registered committee choices.")
        volunteer_id = await self.repository.approve_volunteer_application(
            detail,
            accepted_group_id=resolved_group_id,
        )
        self._invalidate_pending_count_cache()
        await self._send_profile_completion_email(email=detail.email, token=detail.token, base_url=base_url)
        return volunteer_id

    async def approve_volunteer_application_group(
        self,
        group_id: int,
        *,
        accepted_group_id: int,
        base_url: str | None = None,
    ) -> list[int]:
        members = await self.repository.list_group_members(group_id, include_dropped=False)
        active_registration_ids = [
            member.registration_id
            for member in members
            if member.registration_id is not None and member.active
        ]
        if not active_registration_ids:
            raise VolunteerApplicationNotFoundError("Group registration was not found.")
        if any(not member.submitted for member in members if member.active):
            raise VolunteerApplicationConflictError(
                "Kan ikke godkjenne før alle gruppemedlemmer har sendt inn sin søknad."
            )
        volunteer_ids: list[int] = []
        for registration_id in active_registration_ids:
            volunteer_ids.append(
                await self.approve_volunteer_application(
                    registration_id,
                    accepted_group_id=accepted_group_id,
                    base_url=base_url,
                )
            )
        return volunteer_ids

    async def drop_group_invitee(
        self,
        registration_id: int,
        *,
        dropped_by_user_id: int | None = None,
    ) -> None:
        detail = await self.get_volunteer_application_detail(registration_id)
        if detail is None:
            raise VolunteerApplicationNotFoundError(_REGISTRATION_NOT_FOUND)
        if detail.group_role != "invitee" or detail.group_status != "active":
            raise VolunteerApplicationConflictError("Only active group invitees can be removed from a group.")
        await self.repository.drop_group_invitee(registration_id, dropped_by_user_id=dropped_by_user_id)
        self._invalidate_pending_count_cache()

    async def delete_volunteer_application(self, registration_id: int) -> None:
        detail = await self.get_volunteer_application_detail(registration_id)
        if detail is None:
            raise VolunteerApplicationNotFoundError(_REGISTRATION_NOT_FOUND)
        await self.repository.delete_volunteer_application(registration_id)
        self._invalidate_pending_count_cache()
        storage_path = _build_photo_storage_path(detail.photo_sha1, detail.photo_filetype)
        if storage_path and self.storage_service is not None:
            try:
                await to_thread(self.storage_service.remove_photo, storage_path)
            except Exception:
                pass

    async def resend_volunteer_application_invitation(
        self,
        registration_id: int,
        *,
        base_url: str | None = None,
    ) -> VolunteerApplicationDetail:
        detail = await self.get_volunteer_application_detail(registration_id)
        if detail is None:
            raise VolunteerApplicationNotFoundError(_REGISTRATION_NOT_FOUND)
        await self._send_invitation_email(email=detail.email, token=detail.token, base_url=base_url)
        return detail

    def _normalize_friend_emails(
        self,
        friend_emails: list[str] | None,
        *,
        inviter_email: str,
    ) -> list[str]:
        normalized = [email.strip().lower() for email in friend_emails or [] if email and email.strip()]
        if len(normalized) > 2:
            raise VolunteerApplicationFieldValidationError(
                "Du kan legge til maks to venner.",
                {"friendEmails": "Du kan legge til maks to venner."},
            )
        seen: set[str] = {inviter_email}
        field_errors: dict[str, str] = {}
        for index, email in enumerate(normalized):
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                field_errors[str(index)] = "Skriv inn en gyldig e-postadresse."
            elif email in seen:
                field_errors[str(index)] = "E-postadressene må være ulike."
            seen.add(email)
        if field_errors:
            raise VolunteerApplicationFieldValidationError(
                "Én eller flere venneadresser er ugyldige.",
                {"friendEmails": field_errors},
            )
        return normalized

    async def _assert_friend_emails_available(self, friend_emails: list[str]) -> None:
        for index, friend_email in enumerate(friend_emails):
            is_already_volunteer = (
                await self.repository.find_volunteer_id_by_email(friend_email)
            ) is not None
            if is_already_volunteer:
                raise VolunteerApplicationFieldConflictError(
                    "Én av vennene er allerede frivillig.",
                    {"friendEmails": {str(index): "Denne e-postadressen tilhører allerede en frivillig."}},
                )
            has_active_registration = (
                await self.repository.find_active_registration_id_by_email(friend_email)
            ) is not None
            if has_active_registration:
                raise VolunteerApplicationFieldConflictError(
                    "Én av vennene har allerede en aktiv søknad.",
                    {"friendEmails": {str(index): "Denne e-postadressen har allerede en aktiv søknad."}},
                )

    def _ensure_group_members_ready_for_promotion(self, detail: VolunteerApplicationDetail) -> None:
        if not detail.group_id or detail.group_status != "active":
            return
        for member in detail.group_members or []:
            if member.registration_id == detail.registration_id or not member.active:
                continue
            if not member.submitted:
                raise VolunteerApplicationConflictError(
                    "Kan ikke godkjenne før alle gruppemedlemmer har sendt inn sin søknad."
                )

    def _require_storage_service(self) -> StorageService:
        if self.storage_service is None:
            raise NotConfiguredError("Supabase credentials are required for storage integration.")
        return self.storage_service

    def _invalidate_pending_count_cache(self) -> None:
        self._pending_count_cache.pop("pending-count")

    async def _send_invitation_email(self, *, email: str, token: str, base_url: str | None = None) -> None:
        resolved_base_url = (base_url or self.settings.app_public_base_url or "").rstrip("/")
        if not resolved_base_url:
            raise NotConfiguredError("APP_PUBLIC_BASE_URL is required to send registration invitation emails.")
        invitation_url = f"{resolved_base_url}/apply/{token}"
        rendered_email = self.applicant_email_renderer.render_invitation_email(invitation_url=invitation_url)
        await self.email_sender.send_email(
            recipient_email=email,
            subject=rendered_email.subject,
            html_body=rendered_email.html_body,
        )

    async def _send_friend_invitation_email(
        self,
        *,
        email: str,
        token: str,
        inviter_name: str,
        first_choice_group_name: str,
        base_url: str | None = None,
    ) -> None:
        resolved_base_url = (base_url or self.settings.app_public_base_url or "").rstrip("/")
        if not resolved_base_url:
            raise NotConfiguredError("APP_PUBLIC_BASE_URL is required to send registration invitation emails.")
        invitation_url = f"{resolved_base_url}/apply/{token}"
        rendered_email = self.applicant_email_renderer.render_friend_invitation_email(
            invitation_url=invitation_url,
            inviter_name=inviter_name,
            first_choice_group_name=first_choice_group_name,
        )
        await self.email_sender.send_email(
            recipient_email=email,
            subject=rendered_email.subject,
            html_body=rendered_email.html_body,
        )

    async def _send_profile_completion_email(self, *, email: str, token: str, base_url: str | None = None) -> None:
        resolved_base_url = (base_url or self.settings.app_public_base_url or "").rstrip("/")
        if not resolved_base_url:
            raise NotConfiguredError("APP_PUBLIC_BASE_URL is required to send profile completion emails.")
        invitation_url = f"{resolved_base_url}/apply/{token}"
        rendered_email = self.applicant_email_renderer.render_profile_completion_email(invitation_url=invitation_url)
        await self.email_sender.send_email(
            recipient_email=email,
            subject=rendered_email.subject,
            html_body=rendered_email.html_body,
        )


def _parse_recent_registration_cursor(cursor: str | None) -> int | None:
    if cursor is None:
        return None
    stripped = cursor.strip()
    if not stripped:
        return None
    try:
        volunteer_id = int(stripped)
    except ValueError:
        return None
    return volunteer_id if volunteer_id > 0 else None


def _build_full_name(first_name: str | None, last_name: str) -> str:
    return " ".join(part for part in [first_name or "", last_name] if part.strip()).strip() or last_name


def _split_full_name(full_name: str) -> tuple[str | None, str]:
    parts = [part for part in full_name.strip().split() if part]
    if not parts:
        raise VolunteerApplicationValidationError("Navn er påkrevd.")
    if len(parts) == 1:
        return None, parts[0]
    return " ".join(parts[:-1]), parts[-1]


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _sanitize_filename(filename: str) -> str:
    stripped = filename.strip()
    if not stripped:
        return "photo"
    return stripped.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]


def _normalize_extension(filename: str) -> str:
    if "." not in filename:
        raise VolunteerApplicationConflictError("Photos must include a file extension.")
    return filename.rsplit(".", 1)[-1].lower()


def _resolve_content_type(filename: str, content_type: str | None) -> str:
    if content_type:
        return content_type
    extension = _normalize_extension(filename)
    if extension in {"jpg", "jpeg"}:
        return "image/jpeg"
    if extension == "png":
        return "image/png"
    if extension == "webp":
        return "image/webp"
    return "application/octet-stream"


def _build_photo_storage_path(filename_hash: str | None, extension: str | None) -> str | None:
    if not filename_hash or not extension:
        return None
    return f"{filename_hash}.{extension}"
