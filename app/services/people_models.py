from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


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
    photo_url: str | None
    pingvin_points: int = 0
    last_semester_code: int | None = None
    last_semester_label: str | None = None


@dataclass(slots=True)
class PersonListPage:
    items: list[PersonListItem]
    limit: int
    cursor: str | None
    next_cursor: str | None


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
class PersonDetailShell:
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


@dataclass(slots=True)
class PersonRelations:
    next_of_kin: list[NextOfKinItem]
    cards: list[CardItem]


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
    async def list_people_page(self, query: str | None = None, limit: int = 10, cursor: str | None = None) -> PersonListPage: ...
    async def get_person_detail_shell(self, person_id: int) -> PersonDetailShell | None: ...
    async def get_person_history(self, person_id: int, limit: int = 12) -> list[MembershipItem]: ...
    async def get_person_documents(self, person_id: int) -> list[DocumentItem]: ...
    async def get_person_relations(self, person_id: int) -> PersonRelations: ...
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
