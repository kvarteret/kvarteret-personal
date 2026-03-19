from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


class VolunteersServiceError(RuntimeError):
    pass


class VolunteerNotFoundError(VolunteersServiceError):
    pass


class DocumentNotFoundError(VolunteersServiceError):
    pass


class DuplicateDocumentError(VolunteersServiceError):
    pass


class UnsupportedUploadError(VolunteersServiceError):
    pass


class InvalidRoleAssignmentError(VolunteersServiceError):
    pass


class DuplicateRoleAssignmentError(VolunteersServiceError):
    pass


class RoleAssignmentNotFoundError(VolunteersServiceError):
    pass


@dataclass(slots=True)
class VolunteerListItem:
    volunteer_id: int
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
class VolunteerListPage:
    items: list[VolunteerListItem]
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
class RoleAssignmentItem:
    history_id: int
    group_id: int
    group_name: str
    role_id: int | None
    role_name: str | None
    pingvin_points: int
    semester_code: int
    semester_label: str
    contract_signed: bool


@dataclass(slots=True)
class GroupOption:
    group_id: int
    name: str
    active: bool


@dataclass(slots=True)
class AssignmentRoleOption:
    role_id: int
    group_id: int
    role_name: str
    pingvin_points: int


@dataclass(slots=True)
class VolunteerDetail:
    volunteer_id: int
    first_name: str | None
    last_name: str
    full_name: str
    email: str | None
    phone: str | None
    birth_date: date | None
    created_at: datetime
    gender_code: str
    gender_label: str
    address: str | None
    postal_code: str | None
    pingvin_points: int
    photo_url: str | None

@dataclass(slots=True)
class VolunteerRelations:
    next_of_kin: list[NextOfKinItem]
    cards: list[CardItem]


@dataclass(slots=True)
class VolunteerPhotoUploadResult:
    volunteer_id: int
    photo_url: str
    storage_path: str

@dataclass(slots=True)
class VolunteerDocumentUploadResult:
    document_id: int
    volunteer_id: int
    filename: str
    filetype: str | None
    group_id: int | None
    storage_path: str
    download_url: str

class VolunteersServiceProtocol(Protocol):
    async def list_volunteers(self, query: str | None = None, limit: int = 50) -> list[VolunteerListItem]: ...
    async def list_volunteers_page(self, query: str | None = None, limit: int = 10, cursor: str | None = None) -> VolunteerListPage: ...
    async def get_volunteer_detail(self, volunteer_id: int) -> VolunteerDetail | None: ...
    async def list_role_assignments(self, volunteer_id: int, limit: int = 12) -> list[RoleAssignmentItem]: ...
    async def list_volunteer_documents(self, volunteer_id: int) -> list[DocumentItem]: ...
    async def get_volunteer_relations(self, volunteer_id: int) -> VolunteerRelations: ...
    async def list_assignment_groups(self) -> list[GroupOption]: ...
    async def list_assignment_roles(self, group_id: int) -> list[AssignmentRoleOption]: ...
    async def upload_photo(self, volunteer_id: int, filename: str, content: bytes, content_type: str | None) -> VolunteerPhotoUploadResult: ...
    async def delete_photo(self, volunteer_id: int) -> None: ...
    async def update_volunteer_profile(
        self,
        *,
        volunteer_id: int,
        first_name: str | None,
        last_name: str,
        email: str | None,
        phone: str | None,
        birth_date: date | None,
        gender_code: str,
        address: str | None,
        postal_code: str | None,
    ) -> VolunteerDetail: ...
    async def delete_volunteer(self, volunteer_id: int) -> None: ...
    async def add_role_assignment(
        self,
        *,
        volunteer_id: int,
        group_id: int,
        role_id: int,
        year: int,
        term: int,
        contract_signed: bool,
    ) -> None: ...
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
    ) -> None: ...
    async def delete_role_assignment_for_volunteer(self, volunteer_id: int, history_id: int) -> None: ...
    async def upload_document(
        self,
        volunteer_id: int,
        filename: str,
        content: bytes,
        content_type: str | None,
        group_id: int | None = None,
    ) -> VolunteerDocumentUploadResult: ...
    async def delete_document(self, document_id: int) -> None: ...
