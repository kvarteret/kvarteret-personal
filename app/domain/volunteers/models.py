from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from app.shared.coercion import coerce_date, require_datetime
from app.shared.text import build_full_name
from app.domain.volunteers.options import gender_label, normalize_gender_code
from app.shared.semester import format_semester_code


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

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> VolunteerListItem:
        last_code = int(row["last_semester"]) if row.get("last_semester") is not None else None
        return cls(
            volunteer_id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            full_name=build_full_name(row["first_name"], row["last_name"]),
            email=row["email"],
            phone=row["phone"],
            photo_url=None,
            pingvin_points=int(row.get("pingvin_points") or 0),
            last_semester_code=last_code,
            last_semester_label=format_semester_code(last_code),
        )


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

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> RoleAssignmentItem:
        sc = int(row["semester"])
        return cls(
            history_id=int(row["id"]),
            group_id=int(row["group_id"]),
            group_name=row.get("group_name") or f"Group {row['group_id']}",
            role_id=row.get("role_id"),
            role_name=row.get("role_name"),
            pingvin_points=int(row.get("penguin_points") or 0),
            semester_code=sc,
            semester_label=format_semester_code(sc) or str(sc),
            contract_signed=bool(row["contract_signed"]),
        )


@dataclass(slots=True)
class VolunteerRegistrationLogEntry:
    registration_id: int
    created_at: datetime
    source: str
    status: str
    first_choice_group_name: str | None
    second_choice_group_name: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> VolunteerRegistrationLogEntry:
        return cls(
            registration_id=int(row["registration_id"]),
            created_at=require_datetime(row["registration_created_at"]),
            source=row["registration_source"],
            status=row["registration_status"],
            first_choice_group_name=row.get("first_choice_group_name"),
            second_choice_group_name=row.get("second_choice_group_name"),
        )


@dataclass(slots=True)
class VolunteerCourseCompletionItem:
    completion_id: int
    course_id: int
    course_name: str
    completed_semester_code: int
    completed_semester_label: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> VolunteerCourseCompletionItem:
        sc = int(row["completed_semester"])
        return cls(
            completion_id=int(row["id"]),
            course_id=int(row["course_id"]),
            course_name=row["course_name"],
            completed_semester_code=sc,
            completed_semester_label=format_semester_code(sc) or str(sc),
        )


@dataclass(slots=True)
class GroupOption:
    group_id: int
    name: str
    active: bool

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> GroupOption:
        return cls(
            group_id=int(row["id"]),
            name=row["name"],
            active=bool(row["is_active"]),
        )


@dataclass(slots=True)
class AssignmentRoleOption:
    role_id: int
    group_id: int
    role_name: str
    pingvin_points: int

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AssignmentRoleOption:
        return cls(
            role_id=int(row["id"]),
            group_id=int(row["group_id"]),
            role_name=row["name"] or "Uten navn",
            pingvin_points=int(row.get("penguin_points") or 0),
        )


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
    is_active: bool = False

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> VolunteerDetail:
        gc = normalize_gender_code(row.get("gender"))
        return cls(
            volunteer_id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            full_name=build_full_name(row["first_name"], row["last_name"]),
            email=row["email"],
            phone=row["phone"],
            birth_date=coerce_date(row.get("birth_date")),
            created_at=require_datetime(row["created_at"]),
            gender_code=gc,
            gender_label=gender_label(gc),
            address=row["street_address"],
            postal_code=row["postal_code"],
            pingvin_points=int(row.get("pingvin_points") or 0),
            photo_url=None,
            current_discount_level=int(row["current_discount_level"])
            if row.get("current_discount_level") is not None
            else None,
            registration_log_entry=(
                VolunteerRegistrationLogEntry.from_row(row)
                if row.get("registration_id") is not None
                else None
            ),
            is_active=bool(row.get("is_active")),
        )

    @property
    def discount_level_label(self) -> str | None:
        return discount_level_label(self.current_discount_level)


@dataclass(slots=True)
class VolunteerRelations:
    next_of_kin: list[NextOfKinItem]
    cards: list[CardItem]

    @classmethod
    def from_rows(cls, rows: list[dict[str, Any]]) -> VolunteerRelations:
        next_of_kin: list[NextOfKinItem] = []
        cards: list[CardItem] = []
        for row in rows:
            if row["relation_type"] == "kin":
                next_of_kin.append(NextOfKinItem(
                    next_of_kin_id=int(row["relation_id"]),
                    name=row["primary_text"],
                    phone=row["secondary_text"],
                ))
            elif row["relation_type"] == "card":
                cards.append(CardItem(
                    card_id=int(row["relation_id"]),
                    card_number=row["primary_text"],
                ))
        return cls(next_of_kin=next_of_kin, cards=cards)


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
