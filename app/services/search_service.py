from __future__ import annotations

import asyncio
from datetime import date

from app.services.common import build_full_name
from app.services.search_models import SearchFilterList, SearchQuery, SearchRepositoryProtocol, SearchResultItem
from app.services.semester import format_semester_code


class SearchService:
    def __init__(self, repository: SearchRepositoryProtocol) -> None:
        self.repository = repository

    async def search_people(self, query: SearchQuery) -> list[SearchResultItem]:
        initial_people = await self.repository.search_people_by_birth_date_range(
            query.birth_date_after,
            query.birth_date_before,
        )
        ids = {person.person_id for person in initial_people}

        ids = await self._apply_group_filters(query, ids)
        ids = await self._apply_course_filters(query, ids)

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
                full_name=build_full_name(person.first_name, person.last_name),
                pingvin_points=pingvin_points.get(person.person_id, 0),
                last_semester_code=last_semesters.get(person.person_id),
                last_semester_label=format_semester_code(last_semesters.get(person.person_id)),
                birth_date=person.birth_date,
                phone=person.phone,
                email=person.email,
            )
            for person in ordered_people
        ]

    async def _apply_group_filters(self, query: SearchQuery, ids: set[int]) -> set[int]:
        for filter_list, only_current, include_mode in (
            (query.include_groups, False, True),
            (query.include_current_groups, True, True),
            (query.exclude_groups, False, False),
            (query.exclude_current_groups, True, False),
        ):
            ids = await self._apply_membership_filter(filter_list, ids, only_current=only_current, include_mode=include_mode)
        return ids

    async def _apply_course_filters(self, query: SearchQuery, ids: set[int]) -> set[int]:
        for filter_list, include_mode in (
            (query.include_courses, True),
            (query.exclude_courses, False),
        ):
            ids = await self._apply_course_filter(filter_list, ids, include_mode=include_mode)
        return ids

    async def _apply_membership_filter(
        self,
        filter_list: SearchFilterList | None,
        ids: set[int],
        *,
        only_current: bool,
        include_mode: bool,
    ) -> set[int]:
        if filter_list is None or not filter_list.ids or not ids:
            return ids
        history = await self.repository.get_group_history_for_people(
            ids,
            semester_code=_get_current_semester_code() if only_current else None,
        )
        matched_ids = _collect_matching_ids(
            filter_ids=filter_list.ids,
            items=history,
            value_getter=lambda record: record.group_id,
            conjunction=filter_list.conjunction,
        )
        return ids.intersection(matched_ids) if include_mode else ids.difference(matched_ids)

    async def _apply_course_filter(
        self,
        filter_list: SearchFilterList | None,
        ids: set[int],
        *,
        include_mode: bool,
    ) -> set[int]:
        if filter_list is None or not filter_list.ids or not ids:
            return ids
        history = await self.repository.get_course_history_for_people(ids)
        matched_ids = _collect_matching_ids(
            filter_ids=filter_list.ids,
            items=history,
            value_getter=lambda record: record.course_id,
            conjunction=filter_list.conjunction,
        )
        return ids.intersection(matched_ids) if include_mode else ids.difference(matched_ids)


def _collect_matching_ids(*, filter_ids: list[int], items, value_getter, conjunction: bool) -> set[int]:
    juncts: list[set[int]] = []
    for filter_id in filter_ids:
        juncts.append({item.person_id for item in items if value_getter(item) == filter_id})
    return _combine_sets(juncts, conjunction=conjunction)


def _combine_sets(juncts: list[set[int]], *, conjunction: bool) -> set[int]:
    if not juncts:
        return set()
    result = set(juncts[0])
    for next_set in juncts[1:]:
        if conjunction:
            result.intersection_update(next_set)
        else:
            result.update(next_set)
    return result


def _get_current_semester_code(today: date | None = None) -> int:
    current = today or date.today()
    season = 1 if current.month < 7 else 2
    return current.year * 10 + season
