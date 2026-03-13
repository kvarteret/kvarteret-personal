from __future__ import annotations

import mimetypes
from asyncio import to_thread
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from secrets import token_hex
from typing import Protocol

from sqlalchemy import Float, and_, case, delete, exists, func, insert, literal, or_, select, update

from app.cache import TTLCache
from app.config import get_settings
from app.db.session import get_session_factory
from app.db.tables import (
    personal,
    personal_bilde,
    personal_fil,
)
from app.media_tokens import build_document_media_url, build_photo_media_url
from app.postgrest import PostgrestClient, get_postgrest_client
from app.services.semester import format_semester_code
from app.services.storage import StorageService, get_storage_service


class PeopleServiceError(RuntimeError):
    pass


class PersonNotFoundError(PeopleServiceError):
    pass


class DocumentNotFoundError(PeopleServiceError):
    pass


class DuplicateDocumentError(PeopleServiceError):
    pass


class UnsupportedUploadError(PeopleServiceError):
    pass


@dataclass(slots=True)
class PersonListItem:
    person_id: int
    first_name: str | None
    last_name: str
    full_name: str
    email: str | None
    phone: str | None
    birth_date: date | None
    created_at: datetime
    photo_url: str | None


@dataclass(slots=True)
class PersonListPage:
    items: list[PersonListItem]
    limit: int
    offset: int
    next_offset: int | None


@dataclass(slots=True)
class NextOfKinItem:
    next_of_kin_id: int
    name: str
    phone: str


@dataclass(slots=True)
class CardItem:
    card_id: int
    card_number: str


@dataclass(slots=True)
class DocumentItem:
    document_id: int
    filename: str
    filetype: str | None
    group_id: int | None
    created_at: datetime
    storage_path: str
    download_url: str | None


@dataclass(slots=True)
class MembershipItem:
    history_id: int
    group_id: int
    group_name: str
    role_id: int | None
    role_name: str | None
    semester_code: int
    semester_label: str
    contract_signed: bool


@dataclass(slots=True)
class PersonDetail:
    person_id: int
    first_name: str | None
    last_name: str
    full_name: str
    email: str | None
    phone: str | None
    birth_date: date | None
    created_at: datetime
    gender: str
    address: str | None
    postal_code: str | None
    employment_status: int | None
    photo_url: str | None
    documents: list[DocumentItem]
    next_of_kin: list[NextOfKinItem]
    cards: list[CardItem]
    recent_memberships: list[MembershipItem]


@dataclass(slots=True)
class PhotoUploadResult:
    person_id: int
    photo_url: str
    storage_path: str


@dataclass(slots=True)
class DocumentUploadResult:
    document_id: int
    person_id: int
    filename: str
    filetype: str | None
    group_id: int | None
    storage_path: str
    download_url: str


class PeopleServiceProtocol(Protocol):
    async def list_people(self, query: str | None = None, limit: int = 50) -> list[PersonListItem]: ...
    async def list_people_page(self, query: str | None = None, limit: int = 10, offset: int = 0) -> PersonListPage: ...
    async def get_person_detail(self, person_id: int) -> PersonDetail | None: ...
    async def upload_photo(self, person_id: int, filename: str, content: bytes, content_type: str | None) -> PhotoUploadResult: ...
    async def delete_photo(self, person_id: int) -> None: ...
    async def upload_document(
        self,
        person_id: int,
        filename: str,
        content: bytes,
        content_type: str | None,
        group_id: int | None = None,
    ) -> DocumentUploadResult: ...
    async def delete_document(self, document_id: int) -> None: ...


class PeopleService:
    def __init__(
        self,
        storage_service: StorageService | None = None,
        postgrest_client: PostgrestClient | None = None,
    ) -> None:
        self.storage_service = storage_service or get_storage_service()
        self.postgrest_client = postgrest_client
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
        normalized_query = _normalize_search_query(query)
        if normalized_query:
            return await self._search_people_page(normalized_query, safe_limit, safe_offset)
        if self.postgrest_client is None:
            raise RuntimeError("PostgREST-backed people reads are not configured yet.")
        rows = await self.postgrest_client.select_rows(
            "personal",
            select="id,fornavn,etternavn,epost,telefon,fodselsdato,opprettet,personal_bilde(sha1,filetype)",
            order="etternavn.asc,fornavn.asc,id.asc",
            limit=safe_limit + 1,
            offset=safe_offset,
        )
        has_more = len(rows) > safe_limit
        visible_rows = rows[:safe_limit]
        items = [
            PersonListItem(
                person_id=row["id"],
                first_name=row["fornavn"],
                last_name=row["etternavn"],
                full_name=_build_full_name(row["fornavn"], row["etternavn"]),
                email=row["epost"],
                phone=row["telefon"],
                birth_date=_coerce_date(row.get("fodselsdato")),
                created_at=_coerce_datetime(row["opprettet"]),
                photo_url=self._build_photo_url_from_embedded(row.get("personal_bilde")),
            )
            for row in visible_rows
        ]
        return PersonListPage(
            items=items,
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
        if not await self._person_exists(person_id):
            raise PersonNotFoundError(f"Person {person_id} was not found.")

        async with get_session_factory()() as session:
            existing = (
                await session.execute(
                    select(personal_bilde.c.sha1, personal_bilde.c.filetype).where(personal_bilde.c.id_personal == person_id).limit(1)
                )
            ).mappings().first()

        filename_hash = existing["sha1"] if existing else token_hex(20)
        storage_path = f"{filename_hash}.{extension}"
        old_storage_path = (
            f"{existing['sha1']}.{existing['filetype']}" if existing and existing.get("filetype") else None
        )

        await to_thread(self.storage_service.upload_photo, storage_path, content, _resolve_content_type(safe_filename, content_type))
        try:
            async with get_session_factory()() as session:
                async with session.begin():
                    if existing:
                        await session.execute(
                            update(personal_bilde)
                            .where(personal_bilde.c.id_personal == person_id)
                            .values(filetype=extension)
                        )
                    else:
                        await session.execute(
                            insert(personal_bilde).values(id_personal=person_id, sha1=filename_hash, filetype=extension)
                        )
        except Exception:
            await _best_effort_remove(lambda: self.storage_service.remove_photo(storage_path))
            raise

        if old_storage_path and old_storage_path != storage_path:
            await _best_effort_remove(lambda: self.storage_service.remove_photo(old_storage_path))
        self._invalidate_person_cache(person_id)

        return PhotoUploadResult(
            person_id=person_id,
            photo_url=build_photo_media_url(storage_path),
            storage_path=storage_path,
        )

    async def delete_photo(self, person_id: int) -> None:
        async with get_session_factory()() as session:
            row = (
                await session.execute(
                    select(personal_bilde.c.sha1, personal_bilde.c.filetype).where(personal_bilde.c.id_personal == person_id).limit(1)
                )
            ).mappings().first()
        if not row:
            raise PersonNotFoundError(f"Photo for person {person_id} was not found.")
        async with get_session_factory()() as session:
            async with session.begin():
                await session.execute(delete(personal_bilde).where(personal_bilde.c.id_personal == person_id))
        await _best_effort_remove(lambda: self.storage_service.remove_photo(f"{row['sha1']}.{row['filetype']}"))
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
        if not await self._person_exists(person_id):
            raise PersonNotFoundError(f"Person {person_id} was not found.")

        async with get_session_factory()() as session:
            duplicate_exists = await session.scalar(
                select(
                    exists().where(
                        personal_fil.c.id_personal == person_id,
                        func.lower(personal_fil.c.filename) == safe_filename.lower(),
                    )
                )
            )
        if duplicate_exists:
            raise DuplicateDocumentError(f"Document {safe_filename} already exists for person {person_id}.")

        storage_path = _build_document_storage_path(person_id, safe_filename)
        await to_thread(
            self.storage_service.upload_document,
            storage_path,
            content,
            _resolve_content_type(safe_filename, content_type),
        )
        try:
            async with get_session_factory()() as session:
                async with session.begin():
                    row = (
                        await session.execute(
                            insert(personal_fil)
                            .values(
                                id_personal=person_id,
                                gruppekobling=group_id,
                                filename=safe_filename,
                                filetype=extension,
                            )
                            .returning(
                                personal_fil.c.id,
                                personal_fil.c.id_personal,
                                personal_fil.c.gruppekobling,
                                personal_fil.c.filename,
                                personal_fil.c.filetype,
                            )
                        )
                    ).mappings().one()
        except Exception:
            await _best_effort_remove(lambda: self.storage_service.remove_document(storage_path))
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
        async with get_session_factory()() as session:
            row = (
                await session.execute(
                    select(personal_fil.c.id, personal_fil.c.id_personal, personal_fil.c.filename)
                    .where(personal_fil.c.id == document_id)
                    .limit(1)
                )
            ).mappings().first()
        if not row:
            raise DocumentNotFoundError(f"Document {document_id} was not found.")
        async with get_session_factory()() as session:
            async with session.begin():
                await session.execute(delete(personal_fil).where(personal_fil.c.id == document_id))
        await _best_effort_remove(
            lambda: self.storage_service.remove_document(_build_document_storage_path(row["id_personal"], row["filename"]))
        )
        self._invalidate_person_cache(row["id_personal"])

    async def _person_exists(self, person_id: int) -> bool:
        async with get_session_factory()() as session:
            return bool(
                await session.scalar(select(exists().where(personal.c.id == person_id)))
            )

    def _build_photo_url_from_embedded(self, bilde_data) -> str | None:
        if not bilde_data:
            return None
        if isinstance(bilde_data, list):
            bilde_data = bilde_data[0] if bilde_data else None
        if not bilde_data:
            return None
        sha1 = bilde_data.get("sha1")
        filetype = bilde_data.get("filetype")
        if not sha1 or not filetype:
            return None
        return build_photo_media_url(f"{sha1}.{filetype}")

    def _build_document_url(self, person_id: int, filename: str | None) -> str | None:
        if not filename:
            return None
        return build_document_media_url(_build_document_storage_path(person_id, filename))

    def _invalidate_person_cache(self, person_id: int) -> None:
        self._detail_cache.pop(person_id)

    async def _search_people_page(self, normalized_query: str, limit: int, offset: int) -> PersonListPage:
        full_name_search = _searchable_full_name_expr()
        first_name_search = _searchable_field_expr(personal.c.fornavn)
        last_name_search = _searchable_field_expr(personal.c.etternavn)
        email_search = _searchable_field_expr(personal.c.epost)
        phone_search = _searchable_field_expr(personal.c.telefon)

        tokens = normalized_query.split()
        token_filters = [
            or_(
                full_name_search.contains(token),
                first_name_search.contains(token),
                last_name_search.contains(token),
                email_search.contains(token),
                phone_search.contains(token),
                func.word_similarity(full_name_search, token) >= 0.55,
                func.similarity(first_name_search, token) >= 0.40,
                func.similarity(last_name_search, token) >= 0.40,
                func.similarity(email_search, token) >= 0.45,
                func.similarity(phone_search, token) >= 0.85,
            )
            for token in tokens
        ]

        rank_score = literal(0.0, type_=Float())
        rank_score = rank_score + case((full_name_search == normalized_query, 100.0), else_=0.0)
        rank_score = rank_score + case((last_name_search == normalized_query, 45.0), else_=0.0)
        rank_score = rank_score + case((first_name_search == normalized_query, 35.0), else_=0.0)
        rank_score = rank_score + case((full_name_search.startswith(normalized_query), 28.0), else_=0.0)
        rank_score = rank_score + case((full_name_search.contains(normalized_query), 16.0), else_=0.0)
        rank_score = rank_score + case((email_search.contains(normalized_query), 10.0), else_=0.0)
        rank_score = rank_score + case((phone_search.contains(normalized_query), 10.0), else_=0.0)
        rank_score = rank_score + (
            func.greatest(
                func.word_similarity(full_name_search, normalized_query),
                func.similarity(full_name_search, normalized_query),
                func.similarity(first_name_search, normalized_query),
                func.similarity(last_name_search, normalized_query),
                func.similarity(email_search, normalized_query),
                func.similarity(phone_search, normalized_query),
            )
            * 20.0
        )

        for token in tokens:
            rank_score = rank_score + case((full_name_search.contains(token), 4.0), else_=0.0)
            rank_score = rank_score + case((first_name_search.startswith(token), 5.0), else_=0.0)
            rank_score = rank_score + case((last_name_search.startswith(token), 6.0), else_=0.0)
            rank_score = rank_score + case((email_search.contains(token), 2.5), else_=0.0)

        stmt = (
            select(
                personal.c.id,
                personal.c.fornavn,
                personal.c.etternavn,
                personal.c.epost,
                personal.c.telefon,
                personal.c.fodselsdato,
                personal.c.opprettet,
                personal_bilde.c.sha1,
                personal_bilde.c.filetype,
                rank_score.label("rank_score"),
            )
            .select_from(personal.outerjoin(personal_bilde, personal_bilde.c.id_personal == personal.c.id))
            .where(and_(*token_filters))
            .order_by(rank_score.desc(), personal.c.etternavn.asc(), personal.c.fornavn.asc(), personal.c.id.asc())
            .limit(limit + 1)
            .offset(offset)
        )

        async with get_session_factory()() as session:
            rows = (await session.execute(stmt)).mappings().all()

        has_more = len(rows) > limit
        visible_rows = rows[:limit]
        return PersonListPage(
            items=[
                PersonListItem(
                    person_id=row["id"],
                    first_name=row["fornavn"],
                    last_name=row["etternavn"],
                    full_name=_build_full_name(row["fornavn"], row["etternavn"]),
                    email=row["epost"],
                    phone=row["telefon"],
                    birth_date=_coerce_date(row.get("fodselsdato")),
                    created_at=_coerce_datetime(row["opprettet"]),
                    photo_url=self._build_photo_url_from_embedded(
                        {"sha1": row["sha1"], "filetype": row["filetype"]} if row["sha1"] and row["filetype"] else None
                    ),
                )
                for row in visible_rows
            ],
            limit=limit,
            offset=offset,
            next_offset=offset + limit if has_more else None,
        )

    async def _fetch_person_detail(self, person_id: int) -> PersonDetail | None:
        if self.postgrest_client is None:
            raise RuntimeError("PostgREST-backed people reads are not configured yet.")
        rows = await self.postgrest_client.select_rows(
            "personal",
            select=(
                "id,fornavn,etternavn,epost,telefon,fodselsdato,opprettet,kjonn,"
                "gateadresse,postnummerid,arb_status,"
                "personal_bilde(sha1,filetype),"
                "paarorende(id,navn,telefon,opprettet),"
                "personal_kort(id,kortnummer,opprettet),"
                "personal_fil(id,filename,filetype,gruppekobling,opprettet),"
                "historie(id,id_gruppe,id_verv,semester,signert_kontrakt,grupper(navn),verv(id,verv))"
            ),
            filters={"id": f"eq.{person_id}"},
            limit=1,
        )
        if not rows:
            return None
        row = rows[0]
        created_at = _coerce_datetime(row["opprettet"])

        memberships_raw = sorted(
            row.get("historie") or [],
            key=lambda m: (m.get("semester", 0), m.get("id", 0)),
            reverse=True,
        )[:12]

        return PersonDetail(
            person_id=row["id"],
            first_name=row["fornavn"],
            last_name=row["etternavn"],
            full_name=_build_full_name(row["fornavn"], row["etternavn"]),
            email=row["epost"],
            phone=row["telefon"],
            birth_date=_coerce_date(row.get("fodselsdato")),
            created_at=created_at,
            gender=row["kjonn"],
            address=row["gateadresse"],
            postal_code=row["postnummerid"],
            employment_status=row["arb_status"],
            photo_url=self._build_photo_url_from_embedded(row.get("personal_bilde")),
            documents=[
                DocumentItem(
                    document_id=int(item["id"]),
                    filename=item["filename"],
                    filetype=item.get("filetype"),
                    group_id=item.get("gruppekobling"),
                    created_at=_coerce_datetime(item.get("opprettet")) or created_at,
                    storage_path=_build_document_storage_path(person_id, item["filename"]),
                    download_url=self._build_document_url(person_id, item["filename"]),
                )
                for item in sorted(
                    row.get("personal_fil") or [],
                    key=lambda d: (d.get("opprettet") or "", d.get("id", 0)),
                    reverse=True,
                )
            ],
            next_of_kin=[
                NextOfKinItem(
                    next_of_kin_id=int(item["id"]),
                    name=item["navn"],
                    phone=item["telefon"],
                )
                for item in sorted(
                    row.get("paarorende") or [],
                    key=lambda n: (n.get("opprettet") or "", n.get("id", 0)),
                    reverse=True,
                )
            ],
            cards=[
                CardItem(
                    card_id=int(item["id"]),
                    card_number=item["kortnummer"],
                )
                for item in sorted(
                    row.get("personal_kort") or [],
                    key=lambda c: (c.get("opprettet") or "", c.get("id", 0)),
                    reverse=True,
                )
            ],
            recent_memberships=[
                MembershipItem(
                    history_id=int(m["id"]),
                    group_id=int(m["id_gruppe"]),
                    group_name=(m.get("grupper") or {}).get("navn") or f"Group {m['id_gruppe']}",
                    role_id=m.get("id_verv"),
                    role_name=(m.get("verv") or {}).get("verv"),
                    semester_code=int(m["semester"]),
                    semester_label=format_semester_code(int(m["semester"])) or str(m["semester"]),
                    contract_signed=bool(m["signert_kontrakt"]),
                )
                for m in memberships_raw
            ],
        )



def _build_full_name(first_name: str | None, last_name: str | None) -> str:
    parts = [part.strip() for part in [first_name or "", last_name or ""] if part and part.strip()]
    return " ".join(parts) or "Unknown person"


def _build_document_storage_path(person_id: int, filename: str) -> str:
    return f"{person_id}/{filename}"


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _coerce_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _normalize_search_query(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.lower().split())
    return normalized or None


def _searchable_field_expr(column) -> object:
    return func.lower(func.btrim(func.coalesce(column, "")))


def _searchable_full_name_expr() -> object:
    return func.lower(
        func.btrim(
            func.coalesce(personal.c.fornavn, "")
            + literal(" ")
            + func.coalesce(personal.c.etternavn, "")
        )
    )


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


@lru_cache(maxsize=1)
def get_people_service() -> PeopleService:
    try:
        postgrest_client = get_postgrest_client()
    except Exception:
        postgrest_client = None
    return PeopleService(postgrest_client=postgrest_client)
