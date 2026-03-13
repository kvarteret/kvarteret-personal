from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Protocol

from sqlalchemy import func, select

from app.db.session import get_session_factory
from app.db.tables import historie, verv
from app.postgrest import PostgrestClient, get_postgrest_client
from app.services.semester import format_semester_code


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


class DatabaseSearchRepository:
    def __init__(self, postgrest_client: PostgrestClient | None = None) -> None:
        self.postgrest_client = postgrest_client

    async def search_people_by_birth_date_range(
        self,
        birth_date_after: date | None,
        birth_date_before: date | None,
    ) -> list[SearchPersonBase]:
        if self.postgrest_client is None:
            raise RuntimeError("PostgREST-backed search reads are not configured yet.")
        filters: dict[str, str] = {}
        if birth_date_after is not None:
            filters["fodselsdato"] = f"gte.{birth_date_after.isoformat()}"
        if birth_date_before is not None:
            key = "fodselsdato" if "fodselsdato" not in filters else "and"
            if key == "and":
                filters["and"] = f"(fodselsdato.gte.{birth_date_after.isoformat()},fodselsdato.lte.{birth_date_before.isoformat()})"
                filters.pop("fodselsdato", None)
            else:
                filters["fodselsdato"] = f"lte.{birth_date_before.isoformat()}"
        rows = await self.postgrest_client.select_rows(
            "personal",
            select="id,fornavn,etternavn,fodselsdato,telefon,epost",
            filters=filters,
            order="id.asc",
            limit=500,
        )
        return [
            SearchPersonBase(
                person_id=row["id"],
                first_name=row.get("fornavn"),
                last_name=row["etternavn"],
                birth_date=_coerce_date(row.get("fodselsdato")),
                phone=row.get("telefon"),
                email=row.get("epost"),
            )
            for row in rows
        ]

    async def get_group_history_for_people(
        self,
        person_ids: set[int],
        semester_code: int | None = None,
    ) -> list[SearchMembershipFact]:
        if not person_ids:
            return []
        if self.postgrest_client is None:
            raise RuntimeError("PostgREST-backed search reads are not configured yet.")
        ids_str = ",".join(str(pid) for pid in person_ids)
        filters: dict[str, str] = {"id_personal": f"in.({ids_str})"}
        if semester_code is not None:
            filters["semester"] = f"eq.{semester_code}"
        rows = await self.postgrest_client.select_rows(
            "historie",
            select="id_personal,id_gruppe,semester",
            filters=filters,
        )
        return [
            SearchMembershipFact(
                person_id=row["id_personal"],
                group_id=row["id_gruppe"],
                semester_code=row["semester"],
            )
            for row in rows
        ]

    async def get_course_history_for_people(self, person_ids: set[int]) -> list[SearchCourseFact]:
        if not person_ids:
            return []
        if self.postgrest_client is None:
            raise RuntimeError("PostgREST-backed search reads are not configured yet.")
        ids_str = ",".join(str(pid) for pid in person_ids)
        rows = await self.postgrest_client.select_rows(
            "historie_kurs",
            select="id_personal,id_kurs",
            filters={"id_personal": f"in.({ids_str})"},
        )
        return [
            SearchCourseFact(
                person_id=row["id_personal"],
                course_id=row["id_kurs"],
            )
            for row in rows
        ]

    async def get_pingvin_points(self, person_ids: set[int]) -> dict[int, int]:
        if not person_ids:
            return {}
        stmt = (
            select(
                historie.c.id_personal,
                func.coalesce(func.sum(verv.c.pingvinpoeng), 0).label("pingvin_points"),
            )
            .select_from(historie.outerjoin(verv, verv.c.id == historie.c.id_verv))
            .where(historie.c.id_personal.in_(list(person_ids)))
            .group_by(historie.c.id_personal)
        )
        async with get_session_factory()() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return {row["id_personal"]: int(row["pingvin_points"] or 0) for row in rows}

    async def get_last_semesters(self, person_ids: set[int]) -> dict[int, int]:
        if not person_ids:
            return {}
        stmt = (
            select(historie.c.id_personal, func.max(historie.c.semester).label("last_semester"))
            .where(historie.c.id_personal.in_(list(person_ids)))
            .group_by(historie.c.id_personal)
        )
        async with get_session_factory()() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return {row["id_personal"]: int(row["last_semester"]) for row in rows if row["last_semester"] is not None}

    async def get_people_by_ids(self, person_ids: set[int]) -> list[SearchPersonBase]:
        if not person_ids:
            return []
        if self.postgrest_client is None:
            raise RuntimeError("PostgREST-backed search reads are not configured yet.")
        ids_str = ",".join(str(pid) for pid in person_ids)
        rows = await self.postgrest_client.select_rows(
            "personal",
            select="id,fornavn,etternavn,fodselsdato,telefon,epost",
            filters={"id": f"in.({ids_str})"},
        )
        return [
            SearchPersonBase(
                person_id=row["id"],
                first_name=row.get("fornavn"),
                last_name=row["etternavn"],
                birth_date=_coerce_date(row.get("fodselsdato")),
                phone=row.get("telefon"),
                email=row.get("epost"),
            )
            for row in rows
        ]


class SearchService:
    def __init__(self, repository: SearchRepositoryProtocol) -> None:
        self.repository = repository

    async def search_people(self, query: SearchQuery) -> list[SearchResultItem]:
        initial_people = await self.repository.search_people_by_birth_date_range(
            query.birth_date_after,
            query.birth_date_before,
        )
        ids = {person.person_id for person in initial_people}

        if query.include_groups and query.include_groups.ids:
            ids = await self._include_groups(query.include_groups, ids, only_current=False)
        if query.include_current_groups and query.include_current_groups.ids:
            ids = await self._include_groups(query.include_current_groups, ids, only_current=True)
        if query.exclude_groups and query.exclude_groups.ids:
            ids = await self._exclude_groups(query.exclude_groups, ids, only_current=False)
        if query.exclude_current_groups and query.exclude_current_groups.ids:
            ids = await self._exclude_groups(query.exclude_current_groups, ids, only_current=True)
        if query.include_courses and query.include_courses.ids:
            ids = await self._include_courses(query.include_courses, ids)
        if query.exclude_courses and query.exclude_courses.ids:
            ids = await self._exclude_courses(query.exclude_courses, ids)

        pingvin_points, last_semesters = await asyncio.gather(
            self.repository.get_pingvin_points(ids),
            self.repository.get_last_semesters(ids),
        )

        if query.pingvin_points_below is not None:
            ids = {person_id for person_id in ids if pingvin_points.get(person_id, 0) < query.pingvin_points_below}
        if query.pingvin_points_above is not None:
            ids = {person_id for person_id in ids if pingvin_points.get(person_id, 0) > query.pingvin_points_above}

        people = await self.repository.get_people_by_ids(ids)
        ordered_people = sorted(people, key=lambda person: person.person_id, reverse=True)
        return [
            SearchResultItem(
                person_id=person.person_id,
                first_name=person.first_name,
                last_name=person.last_name,
                full_name=_build_full_name(person.first_name, person.last_name),
                pingvin_points=pingvin_points.get(person.person_id, 0),
                last_semester_code=last_semesters.get(person.person_id),
                last_semester_label=format_semester_code(last_semesters.get(person.person_id)),
                birth_date=person.birth_date,
                phone=person.phone,
                email=person.email,
            )
            for person in ordered_people
        ]

    async def _include_groups(
        self,
        filter_list: SearchFilterList,
        ids: set[int],
        *,
        only_current: bool,
    ) -> set[int]:
        history = await self.repository.get_group_history_for_people(
            ids,
            semester_code=_get_current_semester_code() if only_current else None,
        )
        juncts: list[set[int]] = []
        for group_id in filter_list.ids:
            filtered = {record.person_id for record in history if record.group_id == group_id}
            juncts.append(filtered)
        result = _combine_sets(juncts, conjunction=filter_list.conjunction, include_mode=True)
        return ids.intersection(result)

    async def _exclude_groups(
        self,
        filter_list: SearchFilterList,
        ids: set[int],
        *,
        only_current: bool,
    ) -> set[int]:
        history = await self.repository.get_group_history_for_people(
            ids,
            semester_code=_get_current_semester_code() if only_current else None,
        )
        juncts: list[set[int]] = []
        for group_id in filter_list.ids:
            filtered = {record.person_id for record in history if record.group_id == group_id}
            juncts.append(filtered)
        result = _combine_sets(juncts, conjunction=filter_list.conjunction, include_mode=False)
        return ids.difference(result)

    async def _include_courses(self, filter_list: SearchFilterList, ids: set[int]) -> set[int]:
        history = await self.repository.get_course_history_for_people(ids)
        juncts: list[set[int]] = []
        for course_id in filter_list.ids:
            filtered = {record.person_id for record in history if record.course_id == course_id}
            juncts.append(filtered)
        result = _combine_sets(juncts, conjunction=filter_list.conjunction, include_mode=True)
        return ids.intersection(result)

    async def _exclude_courses(self, filter_list: SearchFilterList, ids: set[int]) -> set[int]:
        history = await self.repository.get_course_history_for_people(ids)
        juncts: list[set[int]] = []
        for course_id in filter_list.ids:
            filtered = {record.person_id for record in history if record.course_id == course_id}
            juncts.append(filtered)
        result = _combine_sets(juncts, conjunction=filter_list.conjunction, include_mode=False)
        return ids.difference(result)


def _combine_sets(juncts: list[set[int]], *, conjunction: bool, include_mode: bool) -> set[int]:
    if not juncts:
        return set()
    result = set(juncts[0])
    for next_set in juncts[1:]:
        if include_mode:
            if conjunction:
                result.intersection_update(next_set)
            else:
                result.update(next_set)
        else:
            if conjunction:
                result.update(next_set)
            else:
                result.intersection_update(next_set)
    return result


def _build_full_name(first_name: str | None, last_name: str | None) -> str:
    return " ".join(part for part in [first_name, last_name] if part) or "Unknown person"


def _coerce_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _get_current_semester_code(today: date | None = None) -> int:
    current = today or date.today()
    season = 1 if current.month < 7 else 2
    return current.year * 10 + season


@lru_cache(maxsize=1)
def get_search_service() -> SearchService:
    try:
        postgrest_client = get_postgrest_client()
    except Exception:
        postgrest_client = None
    return SearchService(DatabaseSearchRepository(postgrest_client=postgrest_client))
