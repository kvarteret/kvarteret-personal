from __future__ import annotations

import mimetypes
from asyncio import to_thread
from pathlib import Path
from secrets import token_hex

from app.cache import TTLCache
from app.config import get_settings
from app.errors import NotConfiguredError
from app.media_tokens import build_document_media_url, build_photo_media_url
from app.postgrest import PostgrestClient
from app.services.common import normalize_search_query
from app.services.people_mappers import (
    build_document_storage_path,
    map_person_detail,
    map_person_list_item,
    map_search_person_list_item,
)
from app.services.people_models import (
    CardItem,
    DocumentItem,
    DocumentNotFoundError,
    DocumentUploadResult,
    DuplicateDocumentError,
    MembershipItem,
    NextOfKinItem,
    PeopleServiceError,
    PeopleServiceProtocol,
    PersonDetail,
    PersonListItem,
    PersonListPage,
    PersonNotFoundError,
    PhotoUploadResult,
    UnsupportedUploadError,
)
from app.services.people_repository import PeopleRepository
from app.services.storage import StorageService


class PeopleService:
    def __init__(
        self,
        repository: PeopleRepository | None = None,
        storage_service: StorageService | None = None,
        postgrest_client: PostgrestClient | None = None,
    ) -> None:
        self.repository = repository or PeopleRepository(postgrest_client=postgrest_client)
        self.storage_service = storage_service
        self.detail_cache_ttl_seconds = get_settings().person_detail_cache_ttl_seconds
        self._detail_cache: TTLCache[int, PersonDetail] = TTLCache(
            ttl_seconds=self.detail_cache_ttl_seconds,
            max_entries=2048,
        )

    async def list_people(self, query: str | None = None, limit: int = 50) -> list[PersonListItem]:
        return (await self.list_people_page(query=query, limit=limit, offset=0)).items

    async def list_people_page(self, query: str | None = None, limit: int = 10, offset: int = 0) -> PersonListPage:
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)
        normalized_query = normalize_search_query(query)
        if normalized_query:
            return await self._search_people_page(normalized_query, safe_limit, safe_offset)
        rows = await self.repository.list_people_page(limit=safe_limit + 1, offset=safe_offset)
        has_more = len(rows) > safe_limit
        visible_rows = rows[:safe_limit]
        return PersonListPage(
            items=[map_person_list_item(row) for row in visible_rows],
            limit=safe_limit,
            offset=safe_offset,
            next_offset=safe_offset + safe_limit if has_more else None,
        )

    async def get_person_detail(self, person_id: int) -> PersonDetail | None:
        cached = self._detail_cache.get(person_id)
        if cached is not None:
            return cached

        person = await self._fetch_person_detail(person_id)
        if person is not None:
            self._detail_cache.set(person_id, person)
        else:
            self._detail_cache.pop(person_id)
        return person

    async def upload_photo(self, person_id: int, filename: str, content: bytes, content_type: str | None) -> PhotoUploadResult:
        safe_filename = _sanitize_filename(filename)
        extension = _normalize_extension(safe_filename)
        if extension not in {"jpg", "jpeg", "png", "webp"}:
            raise UnsupportedUploadError("Photos must be jpg, jpeg, png, or webp.")
        if not await self.repository.person_exists(person_id):
            raise PersonNotFoundError(f"Person {person_id} was not found.")

        existing = await self.repository.fetch_photo_record(person_id)

        filename_hash = existing["sha1"] if existing else token_hex(20)
        storage_path = f"{filename_hash}.{extension}"
        old_storage_path = (
            f"{existing['sha1']}.{existing['filetype']}" if existing and existing.get("filetype") else None
        )

        storage_service = self._require_storage_service()
        await to_thread(storage_service.upload_photo, storage_path, content, _resolve_content_type(safe_filename, content_type))
        try:
            await self.repository.save_photo_record(
                person_id=person_id,
                filename_hash=filename_hash,
                extension=extension,
                existing=bool(existing),
            )
        except Exception:
            await _best_effort_remove(lambda: storage_service.remove_photo(storage_path))
            raise

        if old_storage_path and old_storage_path != storage_path:
            await _best_effort_remove(lambda: storage_service.remove_photo(old_storage_path))
        self._invalidate_person_cache(person_id)

        return PhotoUploadResult(
            person_id=person_id,
            photo_url=build_photo_media_url(storage_path),
            storage_path=storage_path,
        )

    async def delete_photo(self, person_id: int) -> None:
        row = await self.repository.fetch_photo_record(person_id)
        if not row:
            raise PersonNotFoundError(f"Photo for person {person_id} was not found.")
        await self.repository.delete_photo_record(person_id)
        storage_service = self._require_storage_service()
        await _best_effort_remove(lambda: storage_service.remove_photo(f"{row['sha1']}.{row['filetype']}"))
        self._invalidate_person_cache(person_id)

    async def upload_document(
        self,
        person_id: int,
        filename: str,
        content: bytes,
        content_type: str | None,
        group_id: int | None = None,
    ) -> DocumentUploadResult:
        safe_filename = _sanitize_filename(filename)
        extension = _normalize_extension(safe_filename)
        if extension not in {"pdf", "jpg", "jpeg", "png"}:
            raise UnsupportedUploadError("Documents must be pdf, jpg, jpeg, or png.")
        if not await self.repository.person_exists(person_id):
            raise PersonNotFoundError(f"Person {person_id} was not found.")
        if await self.repository.document_exists(person_id=person_id, filename=safe_filename):
            raise DuplicateDocumentError(f"Document {safe_filename} already exists for person {person_id}.")

        storage_path = build_document_storage_path(person_id, safe_filename)
        storage_service = self._require_storage_service()
        await to_thread(
            storage_service.upload_document,
            storage_path,
            content,
            _resolve_content_type(safe_filename, content_type),
        )
        try:
            row = await self.repository.create_document_record(
                person_id=person_id,
                group_id=group_id,
                filename=safe_filename,
                extension=extension,
            )
        except Exception:
            await _best_effort_remove(lambda: storage_service.remove_document(storage_path))
            raise
        self._invalidate_person_cache(person_id)

        return DocumentUploadResult(
            document_id=row["id"],
            person_id=row["id_personal"],
            filename=row["filename"],
            filetype=row["filetype"],
            group_id=row["gruppekobling"],
            storage_path=storage_path,
            download_url=build_document_media_url(storage_path),
        )

    async def delete_document(self, document_id: int) -> None:
        row = await self.repository.fetch_document_record(document_id)
        if not row:
            raise DocumentNotFoundError(f"Document {document_id} was not found.")
        await self._delete_document_row(row)

    async def delete_document_for_person(self, person_id: int, document_id: int) -> None:
        row = await self.repository.fetch_document_record(document_id)
        if not row or row["id_personal"] != person_id:
            raise DocumentNotFoundError(f"Document {document_id} was not found.")

        await self._delete_document_row(row)

    def _invalidate_person_cache(self, person_id: int) -> None:
        self._detail_cache.pop(person_id)

    def _require_storage_service(self) -> StorageService:
        if self.storage_service is None:
            raise NotConfiguredError("Storage-backed people writes are not configured yet.")
        return self.storage_service

    async def _search_people_page(self, normalized_query: str, limit: int, offset: int) -> PersonListPage:
        rows = await self.repository.search_people_page(
            normalized_query=normalized_query,
            limit=limit + 1,
            offset=offset,
        )
        has_more = len(rows) > limit
        visible_rows = rows[:limit]
        return PersonListPage(
            items=[map_search_person_list_item(row) for row in visible_rows],
            limit=limit,
            offset=offset,
            next_offset=offset + limit if has_more else None,
        )

    async def _fetch_person_detail(self, person_id: int) -> PersonDetail | None:
        row = await self.repository.fetch_person_detail_row(person_id)
        if row is None:
            return None
        return map_person_detail(row)

    async def _delete_document_row(self, row) -> None:
        await self.repository.delete_document_record(row["id"])
        storage_service = self._require_storage_service()
        await _best_effort_remove(
            lambda: storage_service.remove_document(build_document_storage_path(row["id_personal"], row["filename"]))
        )
        self._invalidate_person_cache(row["id_personal"])


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


def _resolve_content_type(filename: str, provided: str | None) -> str:
    if provided:
        return provided
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


async def _best_effort_remove(remove_action) -> None:
    try:
        await to_thread(remove_action)
    except Exception:
        return None


__all__ = [
    "CardItem",
    "DocumentItem",
    "DocumentNotFoundError",
    "DocumentUploadResult",
    "DuplicateDocumentError",
    "MembershipItem",
    "NextOfKinItem",
    "PeopleService",
    "PeopleServiceError",
    "PeopleServiceProtocol",
    "PersonDetail",
    "PersonListItem",
    "PersonListPage",
    "PersonNotFoundError",
    "PhotoUploadResult",
    "UnsupportedUploadError",
]
