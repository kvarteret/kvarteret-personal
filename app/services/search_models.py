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
    has_active_signed_contract: bool = False
    include_groups: SearchFilterList | None = None
    include_current_groups: SearchFilterList | None = None
    exclude_groups: SearchFilterList | None = None
    exclude_current_groups: SearchFilterList | None = None
    include_courses: SearchFilterList | None = None
    exclude_courses: SearchFilterList | None = None


@dataclass(slots=True)
class SearchResultItem:
    volunteer_id: int
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
    async def search_volunteers(self, query: SearchQuery) -> list[SearchResultItem]: ...
