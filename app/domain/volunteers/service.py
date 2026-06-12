"""Write side of the volunteers module.

Inherits every read model from ``VolunteersQueries`` (list/search,
detail panels, option lists) and adds the writes: profile updates,
relations, position management, the photo pipeline, and offboarding
deletion. Writes invalidate the inherited per-volunteer detail cache.
"""

from __future__ import annotations

import logging
from asyncio import to_thread
from pathlib import Path
from secrets import token_hex

from app.domain.volunteers.models import (
    InvalidVolunteerRelationsError,
    UnsupportedUploadError,
    VolunteerDetail,
    VolunteerNotFoundError,
    VolunteerPhotoUploadResult,
    VolunteerRelations,
)
from app.domain.volunteers.options import normalize_gender_code
from app.domain.volunteers.queries import (
    VolunteersQueries,
    require_media_token_service,
)
from app.domain.volunteers.repository import VolunteersRepository
from app.errors import NotConfiguredError
from app.infrastructure.contact.phone_numbers import normalize_phone_number
from app.infrastructure.media.photo_processing import process_uploaded_photo
from app.infrastructure.storage.service import StorageService
from app.media_tokens import MediaTokenService

cleanup_logger = logging.getLogger(__name__)


class VolunteersService(VolunteersQueries):
    def __init__(
        self,
        repository: VolunteersRepository | None = None,
        storage_service: StorageService | None = None,
        media_token_service: MediaTokenService | None = None,
        detail_cache_ttl_seconds: int | None = None,
        photo_upload_max_bytes: int = 40 * 1024 * 1024,
        photo_max_dimension: int = 2048,
    ) -> None:
        super().__init__(
            media_token_service=media_token_service,
            detail_cache_ttl_seconds=detail_cache_ttl_seconds,
        )
        self.repository = repository
        self.storage_service = storage_service
        self.photo_upload_max_bytes = photo_upload_max_bytes
        self.photo_max_dimension = photo_max_dimension

    async def update_volunteer_profile(
        self,
        *,
        volunteer_id: int,
        first_name: str | None,
        last_name: str,
        email: str | None,
        phone: str | None,
        birth_date,
        gender_code: str,
        address: str | None,
        postal_code: str | None,
    ) -> VolunteerDetail:
        if not await self.repository.volunteer_exists(volunteer_id):
            raise VolunteerNotFoundError(f"Volunteer {volunteer_id} was not found.")
        await self.repository.update_volunteer_profile(
            volunteer_id=volunteer_id,
            first_name=first_name,
            last_name=last_name.strip(),
            email=_normalize_optional_text(email),
            phone=normalize_phone_number(_normalize_optional_text(phone)),
            birth_date=birth_date,
            gender_code=normalize_gender_code(gender_code),
            address=_normalize_optional_text(address),
            postal_code=_normalize_optional_text(postal_code),
        )
        self.invalidate_volunteer_cache(volunteer_id)
        volunteer = await self.get_volunteer_detail(volunteer_id)
        if volunteer is None:
            raise VolunteerNotFoundError(f"Volunteer {volunteer_id} was not found.")
        return volunteer

    async def replace_volunteer_relations(
        self,
        *,
        volunteer_id: int,
        card_numbers: list[str],
        next_of_kin: list[tuple[str, str]],
    ) -> VolunteerRelations:
        if not await self.repository.volunteer_exists(volunteer_id):
            raise VolunteerNotFoundError(f"Volunteer {volunteer_id} was not found.")

        normalized_card_numbers = [
            normalized_card_number
            for card_number in card_numbers
            if (normalized_card_number := _normalize_optional_text(card_number))
            is not None
        ]

        normalized_next_of_kin: list[dict[str, str]] = []
        for raw_name, raw_phone in next_of_kin:
            normalized_name = _normalize_optional_text(raw_name)
            normalized_phone = normalize_phone_number(
                _normalize_optional_text(raw_phone)
            )
            if normalized_name is None and normalized_phone is None:
                continue
            if normalized_name is None or normalized_phone is None:
                raise InvalidVolunteerRelationsError(
                    "Hver pårørende må ha både name og phone."
                )
            normalized_next_of_kin.append(
                {
                    "name": normalized_name,
                    "phone": normalized_phone,
                }
            )

        await self.repository.replace_volunteer_relations(
            volunteer_id=volunteer_id,
            card_numbers=normalized_card_numbers,
            next_of_kin=normalized_next_of_kin,
        )
        self.invalidate_volunteer_cache(volunteer_id)
        return await self.get_volunteer_relations(volunteer_id)

    async def delete_volunteer(self, volunteer_id: int) -> None:
        if not await self.repository.volunteer_exists(volunteer_id):
            raise VolunteerNotFoundError(f"Volunteer {volunteer_id} was not found.")

        photo_row = await self.repository.fetch_photo_record(volunteer_id)
        await self.repository.delete_volunteer(volunteer_id)
        self.invalidate_volunteer_cache(volunteer_id)

        if self.storage_service is None:
            return

        if photo_row and photo_row.get("sha1") and photo_row.get("filetype"):
            await _best_effort_remove(
                lambda: self.storage_service.remove_photo(
                    f"{photo_row['sha1']}.{photo_row['filetype']}"
                )
            )

    async def upload_photo(
        self,
        volunteer_id: int,
        filename: str,
        content: bytes,
        content_type: str | None,
    ) -> VolunteerPhotoUploadResult:
        safe_filename = _sanitize_filename(filename)
        extension = _normalize_extension(safe_filename)
        if extension not in {"jpg", "jpeg", "png", "webp"}:
            raise UnsupportedUploadError("Photos must be jpg, jpeg, png, or webp.")
        if not await self.repository.volunteer_exists(volunteer_id):
            raise VolunteerNotFoundError(f"Volunteer {volunteer_id} was not found.")

        processed_photo = process_uploaded_photo(
            content,
            max_upload_bytes=self.photo_upload_max_bytes,
            max_dimension=self.photo_max_dimension,
        )
        existing = await self.repository.fetch_photo_record(volunteer_id)
        filename_hash = token_hex(20)
        storage_path = f"{filename_hash}.{processed_photo.extension}"
        old_storage_path = (
            f"{existing['sha1']}.{existing['filetype']}"
            if existing and existing.get("filetype")
            else None
        )

        storage_service = self._require_storage_service()
        await to_thread(
            storage_service.upload_photo,
            storage_path,
            processed_photo.content,
            processed_photo.content_type,
        )
        try:
            await self.repository.save_photo_record(
                volunteer_id=volunteer_id,
                filename_hash=filename_hash,
                extension=processed_photo.extension,
                existing=bool(existing),
            )
        except Exception:
            await _best_effort_remove(
                lambda: storage_service.remove_photo(storage_path)
            )
            raise

        if old_storage_path and old_storage_path != storage_path:
            await _best_effort_remove(
                lambda: storage_service.remove_photo(old_storage_path)
            )
        self.invalidate_volunteer_cache(volunteer_id)

        return VolunteerPhotoUploadResult(
            volunteer_id=volunteer_id,
            photo_url=require_media_token_service(
                self.media_token_service
            ).build_photo_media_url(storage_path),
            storage_path=storage_path,
        )

    async def get_photo_storage_path(self, volunteer_id: int) -> str | None:
        row = await self.repository.fetch_photo_record(volunteer_id)
        if not row or not row.get("sha1") or not row.get("filetype"):
            return None
        return f"{row['sha1']}.{row['filetype']}"

    async def delete_photo(self, volunteer_id: int) -> None:
        row = await self.repository.fetch_photo_record(volunteer_id)
        if not row:
            raise VolunteerNotFoundError(
                f"Photo for volunteer {volunteer_id} was not found."
            )
        await self.repository.delete_photo_record(volunteer_id)
        storage_service = self._require_storage_service()
        await _best_effort_remove(
            lambda: storage_service.remove_photo(f"{row['sha1']}.{row['filetype']}")
        )
        self.invalidate_volunteer_cache(volunteer_id)

    def _require_storage_service(self) -> StorageService:
        if self.storage_service is None:
            raise NotConfiguredError(
                "Storage-backed volunteer writes are not configured yet."
            )
        return self.storage_service


def _sanitize_filename(filename: str) -> str:
    safe_name = Path(filename).name.strip()
    if not safe_name:
        raise UnsupportedUploadError("A filename is required.")
    return safe_name


def _normalize_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if not suffix:
        raise UnsupportedUploadError("Uploaded files must include an extension.")
    return suffix


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


async def _best_effort_remove(remove_action) -> None:
    try:
        await to_thread(remove_action)
    except Exception:
        cleanup_logger.warning("storage cleanup failed", exc_info=True)
