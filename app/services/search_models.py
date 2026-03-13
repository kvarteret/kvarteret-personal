from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(slots=True)
class SearchFilterList:
    ids: list[int]
    conjunction: bool = False


@dataclass(slots=True)
class SearchQuery:
    birth_date_before: date | None = None
    birth_date_after: date | None = None
    pingvin_points_below: int | None = None
    pingvin_points_above: int | None = None
    include_groups: SearchFilterList | None = None
    include_current_groups: SearchFilterList | None = None
    exclude_groups: SearchFilterList | None = None
    exclude_current_groups: SearchFilterList | None = None
    include_courses: SearchFilterList | None = None
    exclude_courses: SearchFilterList | None = None


@dataclass(slots=True)
class SearchPersonBase:
    person_id: int
    first_name: str | None
    last_name: str
    birth_date: date | None
    phone: str | None
    email: str | None


@dataclass(slots=True)
class SearchMembershipFact:
    person_id: int
    group_id: int
    semester_code: int


@dataclass(slots=True)
class SearchCourseFact:
    person_id: int
    course_id: int


@dataclass(slots=True)
class SearchResultItem:
    person_id: int
    first_name: str | None
    last_name: str
    full_name: str
    pingvin_points: int
    last_semester_code: int | None
    last_semester_label: str | None
    birth_date: date | None
    phone: str | None
    email: str | None


class SearchRepositoryProtocol(Protocol):
    async def search_people_by_birth_date_range(
        self,
        birth_date_after: date | None,
        birth_date_before: date | None,
    ) -> list[SearchPersonBase]: ...
    async def get_group_history_for_people(
        self,
        person_ids: set[int],
        semester_code: int | None = None,
    ) -> list[SearchMembershipFact]: ...
    async def get_course_history_for_people(self, person_ids: set[int]) -> list[SearchCourseFact]: ...
    async def get_pingvin_points(self, person_ids: set[int]) -> dict[int, int]: ...
    async def get_last_semesters(self, person_ids: set[int]) -> dict[int, int]: ...
    async def get_people_by_ids(self, person_ids: set[int]) -> list[SearchPersonBase]: ...
