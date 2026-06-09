from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


class VolunteersServiceError(RuntimeError):
    pass


class VolunteerNotFoundError(VolunteersServiceError):
    pass


class UnsupportedUploadError(VolunteersServiceError):
    pass


class InvalidRoleAssignmentError(VolunteersServiceError):
    pass


class DuplicateRoleAssignmentError(VolunteersServiceError):
    pass


class RoleAssignmentNotFoundError(VolunteersServiceError):
    pass


class InvalidVolunteerRelationsError(VolunteersServiceError):
    pass


class InvalidCourseCompletionError(VolunteersServiceError):
    pass


class DuplicateCourseCompletionError(VolunteersServiceError):
    pass


def discount_level_label(level: int | None) -> str | None:
    if level == 1:
        return "borg"
    if level == 2:
        return "dorg"
    if level == 3:
        return "arg"
    return None


class CourseCompletionNotFoundError(VolunteersServiceError):
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
class VolunteerSearchOption:
    volunteer_id: int
    full_name: str


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
class VolunteerRegistrationLogEntry:
    registration_id: int
    created_at: datetime
    source: str
    status: str
    first_choice_group_name: str | None
    second_choice_group_name: str | None
    group_id: int | None = None
    group_role: str | None = None
    group_status: str | None = None


@dataclass(slots=True)
class VolunteerCourseCompletionItem:
    completion_id: int
    course_id: int
    course_name: str
    completed_semester_code: int
    completed_semester_label: str


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
    current_discount_level: int | None = None
    registration_log_entry: VolunteerRegistrationLogEntry | None = None

    @property
    def discount_level_label(self) -> str | None:
        return discount_level_label(self.current_discount_level)


@dataclass(slots=True)
class VolunteerRelations:
    next_of_kin: list[NextOfKinItem]
    cards: list[CardItem]


@dataclass(slots=True)
class VolunteerPhotoUploadResult:
    volunteer_id: int
    photo_url: str
    storage_path: str


class VolunteersServiceProtocol(Protocol):
    async def list_volunteers(
        self, query: str | None = None, limit: int = 50
    ) -> list[VolunteerListItem]: ...
    async def list_volunteer_search_options(
        self, query: str, limit: int = 10
    ) -> list[VolunteerSearchOption]: ...
    async def list_volunteers_page(
        self,
        query: str | None = None,
        limit: int = 10,
        cursor: str | None = None,
        only_active: bool = False,
    ) -> VolunteerListPage: ...
    async def get_volunteer_detail(
        self, volunteer_id: int
    ) -> VolunteerDetail | None: ...
    async def get_photo_storage_path(self, volunteer_id: int) -> str | None: ...
    async def find_volunteer_id_by_email(self, email: str) -> int | None: ...
    async def list_role_assignments(
        self, volunteer_id: int, limit: int = 12
    ) -> list[RoleAssignmentItem]: ...
    async def list_course_completions(
        self, volunteer_id: int, limit: int = 100
    ) -> list[VolunteerCourseCompletionItem]: ...
    async def get_volunteer_relations(
        self, volunteer_id: int
    ) -> VolunteerRelations: ...
    async def list_assignment_groups(self) -> list[GroupOption]: ...
    async def list_assignment_roles(
        self, group_id: int
    ) -> list[AssignmentRoleOption]: ...
    async def upload_photo(
        self, volunteer_id: int, filename: str, content: bytes, content_type: str | None
    ) -> VolunteerPhotoUploadResult: ...
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
    async def replace_volunteer_relations(
        self,
        *,
        volunteer_id: int,
        card_numbers: list[str],
        next_of_kin: list[tuple[str, str]],
    ) -> VolunteerRelations: ...
    async def delete_volunteer(self, volunteer_id: int) -> None: ...
    async def add_course_completion(
        self,
        *,
        volunteer_id: int,
        course_id: int,
        year: int,
        term: int,
    ) -> None: ...
    async def delete_course_completion_for_volunteer(
        self, volunteer_id: int, completion_id: int
    ) -> None: ...
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
    async def delete_role_assignment_for_volunteer(
        self, volunteer_id: int, history_id: int
    ) -> None: ...
