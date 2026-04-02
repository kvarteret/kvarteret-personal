from __future__ import annotations

import logging
from asyncio import to_thread
from dataclasses import dataclass
from datetime import date, datetime
from secrets import token_hex, token_urlsafe
from typing import Protocol

from app.cache import TTLCache
from app.config import Settings
from app.errors import NotConfiguredError
from app.infrastructure.email.protocols import EmailSenderProtocol
from app.infrastructure.media.photo_processing import process_uploaded_photo
from app.infrastructure.contact.phone_numbers import require_e164_phone_number
from app.infrastructure.formatting.semester import format_semester_code
from app.infrastructure.storage.service import StorageService

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
class VolunteerApplicationListItem:
    registration_id: int
    token: str
    email: str
    created_at: datetime
    submitted: bool
    first_name: str | None
    last_name: str | None
    phone: str | None
    initial_group_id: int | None = None
    initial_group_name: str | None = None
    initial_role_id: int | None = None
    initial_role_name: str | None = None


@dataclass(slots=True)
class VolunteerApplicationDetail:
    registration_id: int
    token: str
    email: str
    created_at: datetime
    submitted: bool
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
    initial_group_id: int | None = None
    initial_group_name: str | None = None
    initial_role_id: int | None = None
    initial_role_name: str | None = None


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


class VolunteerApplicationsServiceProtocol(Protocol):
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
    async def approve_volunteer_application(self, registration_id: int) -> int: ...
    async def delete_volunteer_application(self, registration_id: int) -> None: ...
    async def resend_volunteer_application_invitation(
        self,
        registration_id: int,
        *,
        base_url: str | None = None,
    ) -> VolunteerApplicationDetail: ...


class VolunteerApplicationsRepositoryProtocol(Protocol):
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
    async def count_pending_volunteer_applications(self) -> int: ...
    async def get_volunteer_application_detail(self, registration_id: int) -> VolunteerApplicationDetail | None: ...
    async def get_volunteer_application_by_token(self, token: str) -> VolunteerApplicationDetail | None: ...
    async def save_submission(
        self,
        *,
        registration_id: int,
        email: str,
        submission: VolunteerApplicationSubmissionInput,
        photo_sha1: str | None,
        photo_filetype: str | None,
    ) -> None: ...
    async def list_group_admin_email_recipients(self, group_id: int) -> list[str]: ...
    async def find_volunteer_id_by_email(self, email: str) -> int | None: ...
    async def approve_volunteer_application(self, registration: VolunteerApplicationDetail) -> int: ...
    async def delete_volunteer_application(self, registration_id: int) -> None: ...


class VolunteerApplicationsService:
    def __init__(
        self,
        settings: Settings,
        repository: VolunteerApplicationsRepositoryProtocol,
        email_sender: EmailSenderProtocol,
        storage_service: StorageService | None = None,
        pending_count_cache_ttl_seconds: int = 30,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.email_sender = email_sender
        self.storage_service = storage_service
        self._pending_count_cache: TTLCache[str, int] = TTLCache(
            ttl_seconds=pending_count_cache_ttl_seconds,
            max_entries=1,
        )

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
        items = [
            RecentVolunteerRegistrationItem(
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
            )
            for row in visible_rows
        ]
        return RecentVolunteerRegistrationPage(
            items=items,
            limit=safe_limit,
            cursor=cursor,
            next_cursor=str(visible_rows[-1]["id"]) if has_more and visible_rows else None,
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
        try:
            submission.phone = require_e164_phone_number(submission.phone)
        except ValueError as exc:
            raise VolunteerApplicationValidationError(str(exc)) from exc

        photo_sha1 = existing.photo_sha1
        photo_filetype = existing.photo_filetype
        old_storage_path = _build_photo_storage_path(existing.photo_sha1, existing.photo_filetype)
        new_storage_path = old_storage_path
        uploaded_new_photo = False
        storage_service: StorageService | None = None

        if not existing.photo_sha1 and not (photo_filename and photo_content):
            raise VolunteerApplicationValidationError("Profilbilde er påkrevd.")

        if photo_filename and photo_content:
            safe_filename = _sanitize_filename(photo_filename)
            extension = _normalize_extension(safe_filename)
            if extension not in {"jpg", "jpeg", "png", "webp"}:
                raise VolunteerApplicationConflictError("Photos must be jpg, jpeg, png, or webp.")
            storage_service = self._require_storage_service()
            photo_sha1 = token_hex(20)
            processed_photo = process_uploaded_photo(
                photo_content,
                max_upload_bytes=self.settings.photo_upload_max_bytes,
                max_dimension=self.settings.photo_max_dimension,
            )
            photo_filetype = processed_photo.extension
            new_storage_path = _build_photo_storage_path(photo_sha1, photo_filetype)
            assert new_storage_path is not None
            await to_thread(
                storage_service.upload_photo,
                new_storage_path,
                processed_photo.content,
                processed_photo.content_type,
            )
            uploaded_new_photo = True

        try:
            await self.repository.save_submission(
                registration_id=existing.registration_id,
                email=existing.email,
                submission=submission,
                photo_sha1=photo_sha1,
                photo_filetype=photo_filetype,
            )
        except Exception:
            if uploaded_new_photo and storage_service is not None and new_storage_path and old_storage_path != new_storage_path:
                try:
                    await to_thread(storage_service.remove_photo, new_storage_path)
                except Exception:
                    pass
            raise
        self._invalidate_pending_count_cache()
        if uploaded_new_photo and old_storage_path and old_storage_path != new_storage_path:
            try:
                await to_thread(self._require_storage_service().remove_photo, old_storage_path)
            except Exception:
                pass
        detail = await self.get_volunteer_application_by_token(token)
        if detail is None:
            raise VolunteerApplicationNotFoundError("Registration token was not found.")
        await self._notify_group_admins_of_submission(detail, base_url=base_url)
        return detail

    async def approve_volunteer_application(self, registration_id: int) -> int:
        detail = await self.get_volunteer_application_detail(registration_id)
        if detail is None:
            raise VolunteerApplicationNotFoundError("Registration was not found.")
        if detail.pending_volunteer_id is None:
            raise VolunteerApplicationConflictError("Registration has not been submitted yet.")
        duplicate_volunteer = await self.repository.find_volunteer_id_by_email(detail.email)
        if duplicate_volunteer is not None:
            raise VolunteerAlreadyExistsError(duplicate_volunteer, detail.email)
        volunteer_id = await self.repository.approve_volunteer_application(detail)
        self._invalidate_pending_count_cache()
        return volunteer_id

    async def delete_volunteer_application(self, registration_id: int) -> None:
        detail = await self.get_volunteer_application_detail(registration_id)
        if detail is None:
            raise VolunteerApplicationNotFoundError("Registration was not found.")
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
            raise VolunteerApplicationNotFoundError("Registration was not found.")
        await self._send_invitation_email(email=detail.email, token=detail.token, base_url=base_url)
        return detail

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
        await self.email_sender.send_email(
            recipient_email=email,
            subject="Velkommen som ny frivillig på Kvarteret!",
            html_body=(
                "Du er invitert til å fullføre registreringen din i Det Akademiske Kvarter."
                "<br><br>"
                f"Åpne denne lenken for å fylle inn detaljene dine:<br><a href=\"{invitation_url}\">{invitation_url}</a>"
                "<br><br>"
                "Hvis du ikke forventet denne invitasjonen, kan du se bort fra e-posten."
            ),
        )

    async def _notify_group_admins_of_submission(
        self,
        registration: VolunteerApplicationDetail,
        *,
        base_url: str | None = None,
    ) -> None:
        if registration.initial_group_id is None:
            return
        recipients = await self.repository.list_group_admin_email_recipients(registration.initial_group_id)
        if not recipients:
            return
        resolved_base_url = (base_url or self.settings.app_public_base_url or "").rstrip("/")
        if not resolved_base_url:
            logger.warning(
                "Skipped group-admin notification for registration %s because no base URL was configured.",
                registration.registration_id,
            )
            return
        review_url = f"{resolved_base_url}/volunteer-applications/{registration.registration_id}"
        group_name = registration.initial_group_name or f"gruppe {registration.initial_group_id}"
        applicant_name = " ".join(
            part for part in [registration.first_name or "", registration.last_name or ""] if part.strip()
        ).strip() or registration.email
        subject = f"Ny frivilligregistrering for {group_name}"
        html_body = (
            f"En ny frivilligregistrering er sendt inn for {group_name}."
            "<br><br>"
            f"Søker: {applicant_name}<br>"
            f"E-post: {registration.email}"
            "<br><br>"
            f"Åpne søknaden for å gå gjennom hele profilen før du godkjenner eller avviser den:<br>"
            f"<a href=\"{review_url}\">{review_url}</a>"
        )
        for recipient in recipients:
            try:
                await self.email_sender.send_email(
                    recipient_email=recipient,
                    subject=subject,
                    html_body=html_body,
                )
            except Exception:
                logger.exception(
                    "Failed to send volunteer application notification for registration %s to %s",
                    registration.registration_id,
                    recipient,
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
