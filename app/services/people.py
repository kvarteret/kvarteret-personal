from __future__ import annotations

import base64
import json
import logging
import mimetypes
from asyncio import to_thread
from pathlib import Path
from secrets import token_hex
from time import perf_counter
from typing import Any

from app.cache import TTLCache
from app.config import get_settings
from app.errors import NotConfiguredError
from app.media_tokens import build_document_media_url, build_photo_media_url
from app.observability import log_operation_timing
from app.services.common import normalize_search_query
from app.services.people_mappers import (
    build_document_storage_path,
    map_document_item,
    map_membership_item,
    map_person_detail_shell,
    map_person_list_item,
    map_relations,
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
    PersonDetailShell,
    PersonListItem,
    PersonListPage,
    PersonNotFoundError,
    PersonRelations,
    PhotoUploadResult,
    UnsupportedUploadError,
)
from app.services.people_repository import PeopleRepository
from app.services.storage import StorageService

logger = logging.getLogger("app.performance")


class PeopleService:
    def __init__(
        self,
        repository: PeopleRepository | None = None,
        storage_service: StorageService | None = None,
    ) -> None:
        self.repository = repository or PeopleRepository()
        self.storage_service = storage_service
        self.detail_cache_ttl_seconds = get_settings().person_detail_cache_ttl_seconds
        self._shell_cache: TTLCache[int, PersonDetailShell] = TTLCache(
            ttl_seconds=self.detail_cache_ttl_seconds,
            max_entries=2048,
        )
        self._history_cache: TTLCache[int, list[MembershipItem]] = TTLCache(
            ttl_seconds=self.detail_cache_ttl_seconds,
            max_entries=2048,
        )
        self._documents_cache: TTLCache[int, list[DocumentItem]] = TTLCache(
            ttl_seconds=self.detail_cache_ttl_seconds,
            max_entries=2048,
        )
        self._relations_cache: TTLCache[int, PersonRelations] = TTLCache(
            ttl_seconds=self.detail_cache_ttl_seconds,
            max_entries=2048,
        )

    async def list_people(self, query: str | None = None, limit: int = 50) -> list[PersonListItem]:
        return (await self.list_people_page(query=query, limit=limit, cursor=None)).items

    async def list_people_page(
        self,
        query: str | None = None,
        limit: int = 10,
        cursor: str | None = None,
    ) -> PersonListPage:
        started_at = perf_counter()
        safe_limit = max(1, min(limit, 100))
        normalized_query = normalize_search_query(query)
        try:
            if normalized_query:
                page = await self._search_people_page(normalized_query, safe_limit, cursor)
            else:
                decoded = _decode_cursor(cursor)
                rows = await self.repository.list_people_page(
                    limit=safe_limit + 1,
                    after_last_name=decoded.get("last_name") if decoded.get("mode") == "browse" else None,
                    after_first_name=decoded.get("first_name") if decoded.get("mode") == "browse" else None,
                    after_person_id=decoded.get("person_id") if decoded.get("mode") == "browse" else None,
                )
                has_more = len(rows) > safe_limit
                visible_rows = rows[:safe_limit]
                page = PersonListPage(
                    items=[map_person_list_item(row) for row in visible_rows],
                    limit=safe_limit,
                    cursor=cursor,
                    next_cursor=_encode_browse_cursor(visible_rows[-1]) if has_more and visible_rows else None,
                )
            return page
        finally:
            log_operation_timing(
                logger,
                operation="people.search" if normalized_query else "people.list",
                started_at=started_at,
                details={"query": normalized_query or "", "limit": safe_limit},
            )

    async def get_person_detail_shell(self, person_id: int) -> PersonDetailShell | None:
        started_at = perf_counter()
        cached = self._shell_cache.get(person_id)
        if cached is not None:
            return cached
        try:
            row = await self.repository.fetch_person_shell_row(person_id)
            if row is None:
                self._shell_cache.pop(person_id)
                return None
            person = map_person_detail_shell(row)
            self._shell_cache.set(person_id, person)
            return person
        finally:
            log_operation_timing(logger, operation="people.detail.shell", started_at=started_at, details={"person_id": person_id})

    async def get_person_history(self, person_id: int, limit: int = 12) -> list[MembershipItem]:
        started_at = perf_counter()
        cached = self._history_cache.get(person_id)
        if cached is not None:
            return cached
        try:
            rows = await self.repository.fetch_person_history_rows(person_id, limit=limit)
            items = [map_membership_item(row) for row in rows]
            self._history_cache.set(person_id, items)
            return items
        finally:
            log_operation_timing(logger, operation="people.detail.history", started_at=started_at, details={"person_id": person_id})

    async def get_person_documents(self, person_id: int) -> list[DocumentItem]:
        started_at = perf_counter()
        cached = self._documents_cache.get(person_id)
        if cached is not None:
            return cached
        try:
            rows = await self.repository.fetch_person_document_rows(person_id)
            items = [map_document_item(person_id, row) for row in rows]
            self._documents_cache.set(person_id, items)
            return items
        finally:
            log_operation_timing(
                logger,
                operation="people.detail.documents",
                started_at=started_at,
                details={"person_id": person_id},
            )

    async def get_person_relations(self, person_id: int) -> PersonRelations:
        started_at = perf_counter()
        cached = self._relations_cache.get(person_id)
        if cached is not None:
            return cached
        try:
            rows = await self.repository.fetch_person_relation_rows(person_id)
            relations = map_relations(rows)
            self._relations_cache.set(person_id, relations)
            return relations
        finally:
            log_operation_timing(
                logger,
                operation="people.detail.relations",
                started_at=started_at,
                details={"person_id": person_id},
            )

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
        self._shell_cache.pop(person_id)
        self._history_cache.pop(person_id)
        self._documents_cache.pop(person_id)
        self._relations_cache.pop(person_id)

    def _require_storage_service(self) -> StorageService:
        if self.storage_service is None:
            raise NotConfiguredError("Storage-backed people writes are not configured yet.")
        return self.storage_service

    async def _search_people_page(self, normalized_query: str, limit: int, cursor: str | None) -> PersonListPage:
        decoded = _decode_cursor(cursor)
        offset = int(decoded.get("offset", 0)) if decoded.get("mode") == "search" else 0
        rows = await self.repository.search_people_page(
            normalized_query=normalized_query,
            limit=limit + 1,
            offset=max(0, offset),
        )
        has_more = len(rows) > limit
        visible_rows = rows[:limit]
        return PersonListPage(
            items=[map_person_list_item(row) for row in visible_rows],
            limit=limit,
            cursor=cursor,
            next_cursor=_encode_cursor({"mode": "search", "offset": offset + limit}) if has_more else None,
        )

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


def _encode_browse_cursor(row: dict[str, Any]) -> str:
    return _encode_cursor(
        {
            "mode": "browse",
            "last_name": row["etternavn"],
            "first_name": row.get("fornavn") or "",
            "person_id": row["id"],
        }
    )


def _encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str | None) -> dict[str, Any]:
    if not cursor:
        return {}
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


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
    "PersonDetailShell",
    "PersonListItem",
    "PersonListPage",
    "PersonNotFoundError",
    "PersonRelations",
    "PhotoUploadResult",
    "UnsupportedUploadError",
]
