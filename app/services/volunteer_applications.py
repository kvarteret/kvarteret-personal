from __future__ import annotations

from asyncio import to_thread
from dataclasses import dataclass
from datetime import date, datetime
from secrets import token_hex, token_urlsafe
from typing import Protocol

from app.cache import TTLCache
from app.errors import NotConfiguredError
from app.services.storage import StorageService


class VolunteerApplicationsError(RuntimeError):
    pass


class VolunteerApplicationNotFoundError(VolunteerApplicationsError):
    pass


class VolunteerApplicationConflictError(VolunteerApplicationsError):
    pass


@dataclass(slots=True)
class VolunteerApplicationInvite:
    registration_id: int
    token: str
    email: str
    created_at: datetime


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
    employment_status: int | None
    photo_sha1: str | None
    photo_filetype: str | None
    photo_url: str | None


@dataclass(slots=True)
class VolunteerApplicationSubmissionInput:
    first_name: str | None
    last_name: str
    phone: str | None
    birth_date: date | None
    gender: str
    address: str | None
    postal_code: str | None
    employment_status: int | None


class VolunteerApplicationsServiceProtocol(Protocol):
    async def create_volunteer_application_invitation(self, email: str) -> VolunteerApplicationInvite: ...
    async def list_volunteer_applications(self) -> list[VolunteerApplicationListItem]: ...
    async def count_pending_volunteer_applications(self) -> int: ...
    async def get_volunteer_application_detail(self, registration_id: int) -> VolunteerApplicationDetail | None: ...
    async def get_volunteer_application_by_token(self, token: str) -> VolunteerApplicationDetail | None: ...
    async def submit_volunteer_application(
        self,
        token: str,
        submission: VolunteerApplicationSubmissionInput,
        *,
        photo_filename: str | None = None,
        photo_content: bytes | None = None,
        photo_content_type: str | None = None,
    ) -> VolunteerApplicationDetail: ...
    async def approve_volunteer_application(self, registration_id: int) -> int: ...
    async def delete_volunteer_application(self, registration_id: int) -> None: ...


class VolunteerApplicationsRepositoryProtocol(Protocol):
    async def create_volunteer_application_invitation(self, *, email: str, token: str) -> VolunteerApplicationInvite: ...
    async def list_volunteer_applications(self) -> list[VolunteerApplicationListItem]: ...
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
    async def find_volunteer_id_by_email(self, email: str) -> int | None: ...
    async def approve_volunteer_application(self, registration: VolunteerApplicationDetail) -> int: ...
    async def delete_volunteer_application(self, registration_id: int) -> None: ...


class VolunteerApplicationsService:
    def __init__(
        self,
        repository: VolunteerApplicationsRepositoryProtocol,
        storage_service: StorageService | None = None,
        pending_count_cache_ttl_seconds: int = 30,
    ) -> None:
        self.repository = repository
        self.storage_service = storage_service
        self._pending_count_cache: TTLCache[str, int] = TTLCache(
            ttl_seconds=pending_count_cache_ttl_seconds,
            max_entries=1,
        )

    async def create_volunteer_application_invitation(self, email: str) -> VolunteerApplicationInvite:
        normalized_email = email.strip().lower()
        if not normalized_email:
            raise VolunteerApplicationConflictError("An email address is required.")
        token = token_urlsafe(24)
        return await self.repository.create_volunteer_application_invitation(email=normalized_email, token=token)

    async def list_volunteer_applications(self) -> list[VolunteerApplicationListItem]:
        return await self.repository.list_volunteer_applications()

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
        photo_filename: str | None = None,
        photo_content: bytes | None = None,
        photo_content_type: str | None = None,
    ) -> VolunteerApplicationDetail:
        existing = await self.get_volunteer_application_by_token(token)
        if existing is None:
            raise VolunteerApplicationNotFoundError("Registration token was not found.")

        photo_sha1 = existing.photo_sha1
        photo_filetype = existing.photo_filetype
        old_storage_path = _build_photo_storage_path(existing.photo_sha1, existing.photo_filetype)
        new_storage_path = old_storage_path
        uploaded_new_photo = False
        storage_service: StorageService | None = None

        if photo_filename and photo_content:
            safe_filename = _sanitize_filename(photo_filename)
            extension = _normalize_extension(safe_filename)
            if extension not in {"jpg", "jpeg", "png", "webp"}:
                raise VolunteerApplicationConflictError("Photos must be jpg, jpeg, png, or webp.")
            storage_service = self._require_storage_service()
            photo_sha1 = existing.photo_sha1 or token_hex(20)
            photo_filetype = extension
            new_storage_path = _build_photo_storage_path(photo_sha1, photo_filetype)
            assert new_storage_path is not None
            await to_thread(
                storage_service.upload_photo,
                new_storage_path,
                photo_content,
                _resolve_content_type(safe_filename, photo_content_type),
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
        return detail

    async def approve_volunteer_application(self, registration_id: int) -> int:
        detail = await self.get_volunteer_application_detail(registration_id)
        if detail is None:
            raise VolunteerApplicationNotFoundError("Registration was not found.")
        if detail.pending_volunteer_id is None:
            raise VolunteerApplicationConflictError("Registration has not been submitted yet.")
        duplicate_volunteer = await self.repository.find_volunteer_id_by_email(detail.email)
        if duplicate_volunteer is not None:
            raise VolunteerApplicationConflictError("A volunteer with this email already exists.")
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

    def _require_storage_service(self) -> StorageService:
        if self.storage_service is None:
            raise NotConfiguredError("Supabase credentials are required for storage integration.")
        return self.storage_service

    def _invalidate_pending_count_cache(self) -> None:
        self._pending_count_cache.pop("pending-count")


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
