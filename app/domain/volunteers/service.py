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
from app.errors import NotConfiguredError
from app.media_tokens import MediaTokenService
from app.observability import log_operation_timing
from app.shared.text import normalize_search_query
from app.infrastructure.media.photo_processing import process_uploaded_photo
from app.infrastructure.contact.phone_numbers import normalize_phone_number
from app.domain.volunteers.mappers import (
    build_document_storage_path,
    map_course_completion_item,
    map_document_item,
    map_group_option,
    map_role_assignment_item,
    map_volunteer_detail,
    map_volunteer_list_item,
    map_relations,
    map_role_option,
)
from app.domain.volunteers.models import (
    AssignmentRoleOption,
    CardItem,
    CourseCompletionNotFoundError,
    DuplicateCourseCompletionError,
    DuplicateRoleAssignmentError,
    DuplicateDocumentError,
    DocumentItem,
    DocumentNotFoundError,
    GroupOption,
    InvalidCourseCompletionError,
    InvalidVolunteerRelationsError,
    InvalidRoleAssignmentError,
    NextOfKinItem,
    RoleAssignmentItem,
    RoleAssignmentNotFoundError,
    UnsupportedUploadError,
    VolunteerDetail,
    VolunteerDocumentUploadResult,
    VolunteerListItem,
    VolunteerListPage,
    VolunteerCourseCompletionItem,
    VolunteerNotFoundError,
    VolunteerPhotoUploadResult,
    VolunteerRelations,
    VolunteerSearchOption,
    VolunteersServiceError,
    VolunteersServiceProtocol,
)
from app.domain.volunteers.options import normalize_gender_code
from app.domain.volunteers.repository import VolunteersRepository
from app.infrastructure.formatting.semester import format_semester_code
from app.infrastructure.storage.service import StorageService

logger = logging.getLogger("app.performance")
cleanup_logger = logging.getLogger(__name__)


class VolunteersService:
    def __init__(
        self,
        repository: VolunteersRepository | None = None,
        storage_service: StorageService | None = None,
        media_token_service: MediaTokenService | None = None,
        detail_cache_ttl_seconds: int | None = None,
        photo_upload_max_bytes: int = 40 * 1024 * 1024,
        photo_max_dimension: int = 2048,
    ) -> None:
        self.repository = repository or VolunteersRepository()
        self.storage_service = storage_service
        self.media_token_service = media_token_service
        self.detail_cache_ttl_seconds = detail_cache_ttl_seconds or 300
        self.photo_upload_max_bytes = photo_upload_max_bytes
        self.photo_max_dimension = photo_max_dimension
        self._cache: TTLCache[int, dict[str, Any]] = TTLCache(
            ttl_seconds=self.detail_cache_ttl_seconds,
            max_entries=2048,
        )

    async def list_volunteers(self, query: str | None = None, limit: int = 50) -> list[VolunteerListItem]:
        return (await self.list_volunteers_page(query=query, limit=limit, cursor=None)).items

    async def list_volunteer_search_options(self, query: str, limit: int = 10) -> list[VolunteerSearchOption]:
        normalized_query = normalize_search_query(query)
        if not normalized_query or len(normalized_query) < 2:
            return []
        items = await self.list_volunteers(query=normalized_query, limit=max(1, min(limit * 2, 100)))
        return [
            VolunteerSearchOption(
                volunteer_id=item.volunteer_id,
                full_name=item.full_name,
            )
            for item in sorted(items, key=lambda item: (item.full_name.lower(), item.volunteer_id))[:limit]
        ]

    async def list_volunteers_page(
        self,
        query: str | None = None,
        limit: int = 10,
        cursor: str | None = None,
    ) -> VolunteerListPage:
        started_at = perf_counter()
        safe_limit = max(1, min(limit, 100))
        normalized_query = normalize_search_query(query)
        try:
            if normalized_query:
                page = await self._search_volunteers_page(normalized_query, safe_limit, cursor)
            else:
                decoded = _decode_cursor(cursor)
                rows = await self.repository.list_volunteers_page(
                    limit=safe_limit + 1,
                    after_last_name=decoded.get("last_name") if decoded.get("mode") == "browse" else None,
                    after_first_name=decoded.get("first_name") if decoded.get("mode") == "browse" else None,
                    after_volunteer_id=decoded.get("volunteer_id") if decoded.get("mode") == "browse" else None,
                )
                has_more = len(rows) > safe_limit
                visible_rows = rows[:safe_limit]
                items = [map_volunteer_list_item(row) for row in visible_rows]
                for item, row in zip(items, visible_rows, strict=False):
                    item.photo_url = _build_photo_url(self.media_token_service, row.get("sha1"), row.get("filetype"))
                page = VolunteerListPage(
                    items=items,
                    limit=safe_limit,
                    cursor=cursor,
                    next_cursor=_encode_browse_cursor(visible_rows[-1]) if has_more and visible_rows else None,
                )
            return page
        finally:
            log_operation_timing(
                logger,
                operation="volunteers.search" if normalized_query else "volunteers.list",
                started_at=started_at,
                details={"query": normalized_query or "", "limit": safe_limit},
            )

    async def get_volunteer_detail(self, volunteer_id: int) -> VolunteerDetail | None:
        started_at = perf_counter()
        cached = self._cache_get(volunteer_id, "shell")
        if cached is not None:
            return cached
        try:
            row = await self.repository.fetch_volunteer_shell_row(volunteer_id)
            if row is None:
                return None
            volunteer = map_volunteer_detail(row)
            volunteer.photo_url = _build_photo_url(self.media_token_service, row.get("sha1"), row.get("filetype"))
            self._cache_set(volunteer_id, "shell", volunteer)
            return volunteer
        finally:
            log_operation_timing(
                logger,
                operation="volunteers.detail.shell",
                started_at=started_at,
                details={"volunteer_id": volunteer_id},
            )

    async def list_role_assignments(self, volunteer_id: int, limit: int = 12) -> list[RoleAssignmentItem]:
        started_at = perf_counter()
        cached = self._cache_get(volunteer_id, "history")
        if cached is not None:
            return cached
        try:
            rows = await self.repository.fetch_volunteer_role_assignment_rows(volunteer_id, limit=limit)
            items = [map_role_assignment_item(row) for row in rows]
            self._cache_set(volunteer_id, "history", items)
            return items
        finally:
            log_operation_timing(
                logger,
                operation="volunteers.detail.role_assignments",
                started_at=started_at,
                details={"volunteer_id": volunteer_id},
            )

    async def list_course_completions(
        self,
        volunteer_id: int,
        limit: int = 100,
    ) -> list[VolunteerCourseCompletionItem]:
        started_at = perf_counter()
        cached = self._cache_get(volunteer_id, "course_completions")
        if cached is not None:
            return cached
        try:
            rows = await self.repository.fetch_volunteer_course_completion_rows(volunteer_id, limit=limit)
            items = [map_course_completion_item(row) for row in rows]
            self._cache_set(volunteer_id, "course_completions", items)
            return items
        finally:
            log_operation_timing(
                logger,
                operation="volunteers.detail.course_completions",
                started_at=started_at,
                details={"volunteer_id": volunteer_id},
            )

    async def list_volunteer_documents(self, volunteer_id: int) -> list[DocumentItem]:
        started_at = perf_counter()
        cached = self._cache_get(volunteer_id, "documents")
        if cached is not None:
            return cached
        try:
            rows = await self.repository.fetch_volunteer_document_rows(volunteer_id)
            items = [map_document_item(volunteer_id, row) for row in rows]
            for item in items:
                item.download_url = _build_document_url(self.media_token_service, volunteer_id, item.filename)
            self._cache_set(volunteer_id, "documents", items)
            return items
        finally:
            log_operation_timing(
                logger,
                operation="volunteers.detail.documents",
                started_at=started_at,
                details={"volunteer_id": volunteer_id},
            )

    async def get_volunteer_relations(self, volunteer_id: int) -> VolunteerRelations:
        started_at = perf_counter()
        cached = self._cache_get(volunteer_id, "relations")
        if cached is not None:
            return cached
        try:
            rows = await self.repository.fetch_volunteer_relation_rows(volunteer_id)
            relations = map_relations(rows)
            self._cache_set(volunteer_id, "relations", relations)
            return relations
        finally:
            log_operation_timing(
                logger,
                operation="volunteers.detail.relations",
                started_at=started_at,
                details={"volunteer_id": volunteer_id},
            )

    async def list_assignment_groups(self) -> list[GroupOption]:
        rows = await self.repository.list_assignment_group_rows()
        return [map_group_option(row) for row in rows]

    async def list_assignment_roles(self, group_id: int) -> list[AssignmentRoleOption]:
        rows = await self.repository.list_assignment_role_rows(group_id)
        return [map_role_option(row) for row in rows]

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
        self._invalidate_volunteer_cache(volunteer_id)
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
            if (normalized_card_number := _normalize_optional_text(card_number)) is not None
        ]

        normalized_next_of_kin: list[dict[str, str]] = []
        for raw_name, raw_phone in next_of_kin:
            normalized_name = _normalize_optional_text(raw_name)
            normalized_phone = normalize_phone_number(_normalize_optional_text(raw_phone))
            if normalized_name is None and normalized_phone is None:
                continue
            if normalized_name is None or normalized_phone is None:
                raise InvalidVolunteerRelationsError("Hver pårørende må ha både navn og telefon.")
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
        self._invalidate_volunteer_cache(volunteer_id)
        return await self.get_volunteer_relations(volunteer_id)

    async def delete_volunteer(self, volunteer_id: int) -> None:
        if not await self.repository.volunteer_exists(volunteer_id):
            raise VolunteerNotFoundError(f"Volunteer {volunteer_id} was not found.")

        photo_row = await self.repository.fetch_photo_record(volunteer_id)
        document_rows = await self.repository.fetch_volunteer_document_rows(volunteer_id)

        await self.repository.delete_volunteer(volunteer_id)
        self._invalidate_volunteer_cache(volunteer_id)

        if self.storage_service is None:
            return

        if photo_row and photo_row.get("sha1") and photo_row.get("filetype"):
            await _best_effort_remove(
                lambda: self.storage_service.remove_photo(f"{photo_row['sha1']}.{photo_row['filetype']}")
            )

        for row in document_rows:
            if row.get("filename"):
                await _best_effort_remove(
                    lambda filename=row["filename"]: self.storage_service.remove_document(
                        build_document_storage_path(volunteer_id, filename)
                    )
                )

    async def add_course_completion(
        self,
        *,
        volunteer_id: int,
        course_id: int,
        year: int,
        term: int,
    ) -> None:
        semester_code = _build_semester_code(year=year, term=term, error_cls=InvalidCourseCompletionError)
        if not await self.repository.volunteer_exists(volunteer_id):
            raise VolunteerNotFoundError(f"Volunteer {volunteer_id} was not found.")
        if not await self.repository.course_exists(course_id):
            raise InvalidCourseCompletionError("Selected course was not found.")
        if await self.repository.course_completion_exists(
            volunteer_id=volunteer_id,
            course_id=course_id,
            semester_code=semester_code,
        ):
            raise DuplicateCourseCompletionError("Dette kurset er allerede registrert for valgt semester.")
        await self.repository.create_course_completion(
            volunteer_id=volunteer_id,
            course_id=course_id,
            semester_code=semester_code,
        )
        self._invalidate_volunteer_cache(volunteer_id)

    async def delete_course_completion_for_volunteer(self, volunteer_id: int, completion_id: int) -> None:
        row = await self.repository.fetch_course_completion_record(completion_id)
        if not row or row["id_personal"] != volunteer_id:
            raise CourseCompletionNotFoundError(f"Course completion {completion_id} was not found.")
        await self.repository.delete_course_completion(completion_id)
        self._invalidate_volunteer_cache(volunteer_id)

    async def add_role_assignment(
        self,
        *,
        volunteer_id: int,
        group_id: int,
        role_id: int,
        year: int,
        term: int,
        contract_signed: bool,
    ) -> None:
        semester_code = _build_semester_code(year=year, term=term, error_cls=InvalidRoleAssignmentError)
        if not await self.repository.volunteer_exists(volunteer_id):
            raise VolunteerNotFoundError(f"Volunteer {volunteer_id} was not found.")
        if not await self.repository.role_belongs_to_group(group_id=group_id, role_id=role_id):
            raise InvalidRoleAssignmentError("Selected verv does not belong to the selected group.")
        if await self.repository.role_assignment_exists(
            volunteer_id=volunteer_id,
            group_id=group_id,
            role_id=role_id,
            semester_code=semester_code,
        ):
            raise DuplicateRoleAssignmentError("This verv is already registered for the selected semester.")
        await self.repository.create_role_assignment(
            volunteer_id=volunteer_id,
            group_id=group_id,
            role_id=role_id,
            semester_code=semester_code,
            contract_signed=contract_signed,
        )
        self._invalidate_volunteer_cache(volunteer_id)

    async def update_role_assignment_for_volunteer(
        self,
        volunteer_id: int,
        history_id: int,
        *,
        group_id: int,
        role_id: int,
        year: int,
        term: int,
        contract_signed: bool,
    ) -> None:
        row = await self.repository.fetch_role_assignment_record(history_id)
        if not row or row["id_personal"] != volunteer_id:
            raise RoleAssignmentNotFoundError(f"Role assignment {history_id} was not found.")
        semester_code = _build_semester_code(year=year, term=term, error_cls=InvalidRoleAssignmentError)
        if not await self.repository.role_belongs_to_group(group_id=group_id, role_id=role_id):
            raise InvalidRoleAssignmentError("Selected verv does not belong to the selected group.")
        if await self.repository.role_assignment_exists(
            volunteer_id=volunteer_id,
            group_id=group_id,
            role_id=role_id,
            semester_code=semester_code,
            exclude_history_id=history_id,
        ):
            raise DuplicateRoleAssignmentError("This verv is already registered for the selected semester.")
        await self.repository.update_role_assignment(
            history_id,
            group_id=group_id,
            role_id=role_id,
            semester_code=semester_code,
            contract_signed=contract_signed,
        )
        self._invalidate_volunteer_cache(volunteer_id)

    async def delete_role_assignment_for_volunteer(self, volunteer_id: int, history_id: int) -> None:
        row = await self.repository.fetch_role_assignment_record(history_id)
        if not row or row["id_personal"] != volunteer_id:
            raise RoleAssignmentNotFoundError(f"Role assignment {history_id} was not found.")
        await self.repository.delete_role_assignment(history_id)
        self._invalidate_volunteer_cache(volunteer_id)

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
            f"{existing['sha1']}.{existing['filetype']}" if existing and existing.get("filetype") else None
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
            await _best_effort_remove(lambda: storage_service.remove_photo(storage_path))
            raise

        if old_storage_path and old_storage_path != storage_path:
            await _best_effort_remove(lambda: storage_service.remove_photo(old_storage_path))
        self._invalidate_volunteer_cache(volunteer_id)

        return VolunteerPhotoUploadResult(
            volunteer_id=volunteer_id,
            photo_url=_require_media_token_service(self.media_token_service).build_photo_media_url(storage_path),
            storage_path=storage_path,
        )

    async def get_photo_storage_path(self, volunteer_id: int) -> str | None:
        row = await self.repository.fetch_photo_record(volunteer_id)
        if not row or not row.get("sha1") or not row.get("filetype"):
            return None
        return f"{row['sha1']}.{row['filetype']}"

    async def find_volunteer_id_by_email(self, email: str) -> int | None:
        normalized = email.strip().lower()
        if not normalized:
            return None
        return await self.repository.find_volunteer_id_by_email(normalized)

    async def delete_photo(self, volunteer_id: int) -> None:
        row = await self.repository.fetch_photo_record(volunteer_id)
        if not row:
            raise VolunteerNotFoundError(f"Photo for volunteer {volunteer_id} was not found.")
        await self.repository.delete_photo_record(volunteer_id)
        storage_service = self._require_storage_service()
        await _best_effort_remove(lambda: storage_service.remove_photo(f"{row['sha1']}.{row['filetype']}"))
        self._invalidate_volunteer_cache(volunteer_id)

    async def upload_document(
        self,
        volunteer_id: int,
        filename: str,
        content: bytes,
        content_type: str | None,
        group_id: int | None = None,
    ) -> VolunteerDocumentUploadResult:
        safe_filename = _sanitize_filename(filename)
        extension = _normalize_extension(safe_filename)
        if extension not in {"pdf", "jpg", "jpeg", "png"}:
            raise UnsupportedUploadError("Documents must be pdf, jpg, jpeg, or png.")
        if not await self.repository.volunteer_exists(volunteer_id):
            raise VolunteerNotFoundError(f"Volunteer {volunteer_id} was not found.")
        if await self.repository.document_exists(volunteer_id=volunteer_id, filename=safe_filename):
            raise DuplicateDocumentError(f"Document {safe_filename} already exists for volunteer {volunteer_id}.")

        storage_path = build_document_storage_path(volunteer_id, safe_filename)
        storage_service = self._require_storage_service()
        await to_thread(
            storage_service.upload_document,
            storage_path,
            content,
            _resolve_content_type(safe_filename, content_type),
        )
        try:
            row = await self.repository.create_document_record(
                volunteer_id=volunteer_id,
                group_id=group_id,
                filename=safe_filename,
                extension=extension,
            )
        except Exception:
            await _best_effort_remove(lambda: storage_service.remove_document(storage_path))
            raise
        self._invalidate_volunteer_cache(volunteer_id)

        return VolunteerDocumentUploadResult(
            document_id=row["id"],
            volunteer_id=row["id_personal"],
            filename=row["filename"],
            filetype=row["filetype"],
            group_id=row["gruppekobling"],
            storage_path=storage_path,
            download_url=_require_media_token_service(self.media_token_service).build_document_media_url(storage_path),
        )

    async def delete_document(self, document_id: int) -> None:
        row = await self.repository.fetch_document_record(document_id)
        if not row:
            raise DocumentNotFoundError(f"Document {document_id} was not found.")
        await self._delete_document_row(row)

    async def delete_document_for_volunteer(self, volunteer_id: int, document_id: int) -> None:
        row = await self.repository.fetch_document_record(document_id)
        if not row or row["id_personal"] != volunteer_id:
            raise DocumentNotFoundError(f"Document {document_id} was not found.")
        await self._delete_document_row(row)

    def _invalidate_volunteer_cache(self, volunteer_id: int) -> None:
        self._cache.pop(volunteer_id)

    def _cache_get(self, volunteer_id: int, key: str):
        namespace = self._cache.get(volunteer_id)
        return namespace.get(key) if namespace is not None else None

    def _cache_set(self, volunteer_id: int, key: str, value) -> None:
        namespace = dict(self._cache.get(volunteer_id) or {})
        namespace[key] = value
        self._cache.set(volunteer_id, namespace)

    def _require_storage_service(self) -> StorageService:
        if self.storage_service is None:
            raise NotConfiguredError("Storage-backed volunteer writes are not configured yet.")
        return self.storage_service

    async def _search_volunteers_page(self, normalized_query: str, limit: int, cursor: str | None) -> VolunteerListPage:
        decoded = _decode_cursor(cursor)
        offset = int(decoded.get("offset", 0)) if decoded.get("mode") == "search" else 0
        rows = await self.repository.search_volunteers_page(
            normalized_query=normalized_query,
            limit=limit + 1,
            offset=max(0, min(offset, 10_000)),
        )
        has_more = len(rows) > limit
        visible_rows = rows[:limit]
        return VolunteerListPage(
            items=[
                _with_photo_url(
                    map_volunteer_list_item(row),
                    self.media_token_service,
                    row.get("sha1"),
                    row.get("filetype"),
                )
                for row in visible_rows
            ],
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
        self._invalidate_volunteer_cache(row["id_personal"])


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


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _build_semester_code(*, year: int, term: int, error_cls: type[VolunteersServiceError]) -> int:
    if year < 1900 or year > 3000:
        raise error_cls("Year must be between 1900 and 3000.")
    if term not in {1, 2}:
        raise error_cls("Semester must be Vår or Høst.")
    semester_code = year * 10 + term
    if not format_semester_code(semester_code):
        raise error_cls("Unsupported semester code.")
    return semester_code


def _require_media_token_service(media_token_service: MediaTokenService | None) -> MediaTokenService:
    if media_token_service is None:
        raise RuntimeError("A media token service must be configured before building media URLs.")
    return media_token_service


def _build_photo_url(media_token_service: MediaTokenService | None, sha1: str | None, filetype: str | None) -> str | None:
    if not sha1 or not filetype:
        return None
    return _require_media_token_service(media_token_service).build_photo_media_url(f"{sha1}.{filetype}")


def _build_document_url(media_token_service: MediaTokenService | None, volunteer_id: int, filename: str | None) -> str | None:
    if not filename:
        return None
    return _require_media_token_service(media_token_service).build_document_media_url(
        build_document_storage_path(volunteer_id, filename)
    )


def _with_photo_url(
    item: VolunteerListItem,
    media_token_service: MediaTokenService | None,
    sha1: str | None,
    filetype: str | None,
) -> VolunteerListItem:
    item.photo_url = _build_photo_url(media_token_service, sha1, filetype)
    return item


def _encode_browse_cursor(row: dict[str, Any]) -> str:
    return _encode_cursor(
        {
            "mode": "browse",
            "last_name": row["etternavn"],
            "first_name": row.get("fornavn") or "",
            "volunteer_id": row["id"],
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
        cleanup_logger.warning("storage cleanup failed", exc_info=True)
