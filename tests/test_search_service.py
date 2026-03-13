from __future__ import annotations

from datetime import date

import pytest

from app.services.search import (
    SearchCourseFact,
    SearchFilterList,
    SearchMembershipFact,
    SearchPersonBase,
    SearchQuery,
    SearchService,
)


class FakeSearchRepository:
    def __init__(self) -> None:
        self.people = [
            SearchPersonBase(1, "Sample", "Person", date(1815, 12, 10), "1", "person.one@example.test"),
            SearchPersonBase(2, "Second", "Person", date(1906, 12, 9), "2", "person.two@example.test"),
            SearchPersonBase(3, "Third", "Person", date(1969, 12, 28), "3", "person.three@example.test"),
        ]
        self.group_history = [
            SearchMembershipFact(1, 10, 20261),
            SearchMembershipFact(1, 11, 20262),
            SearchMembershipFact(2, 10, 20262),
            SearchMembershipFact(3, 12, 20262),
        ]
        self.course_history = [
            SearchCourseFact(1, 20),
            SearchCourseFact(2, 21),
            SearchCourseFact(2, 20),
        ]
        self.pingvin_points = {1: 5, 2: 12, 3: 1}
        self.last_semesters = {1: 20262, 2: 20262, 3: 20262}

    async def search_people_by_birth_date_range(self, birth_date_after, birth_date_before):
        result = []
        for person in self.people:
            if birth_date_after is not None and (person.birth_date is None or person.birth_date < birth_date_after):
                continue
            if birth_date_before is not None and (person.birth_date is None or person.birth_date > birth_date_before):
                continue
            result.append(person)
        return result

    async def get_group_history_for_people(self, person_ids: set[int], semester_code: int | None = None):
        return [
            row
            for row in self.group_history
            if row.person_id in person_ids and (semester_code is None or row.semester_code == semester_code)
        ]

    async def get_course_history_for_people(self, person_ids: set[int]):
        return [row for row in self.course_history if row.person_id in person_ids]

    async def get_pingvin_points(self, person_ids: set[int]):
        return {person_id: self.pingvin_points.get(person_id, 0) for person_id in person_ids}

    async def get_last_semesters(self, person_ids: set[int]):
        return {person_id: self.last_semesters.get(person_id, 0) for person_id in person_ids}

    async def get_people_by_ids(self, person_ids: set[int]):
        return [person for person in self.people if person.person_id in person_ids]


@pytest.mark.asyncio
async def test_search_service_includes_groups_with_union_logic() -> None:
    service = SearchService(FakeSearchRepository())

    results = await service.search_people(
        SearchQuery(include_groups=SearchFilterList(ids=[10, 12], conjunction=False))
    )

    assert [result.person_id for result in results] == [3, 2, 1]


@pytest.mark.asyncio
async def test_search_service_includes_groups_with_intersection_logic() -> None:
    service = SearchService(FakeSearchRepository())

    results = await service.search_people(
        SearchQuery(include_groups=SearchFilterList(ids=[10, 11], conjunction=True))
    )

    assert [result.person_id for result in results] == [1]


@pytest.mark.asyncio
async def test_search_service_excludes_courses_and_filters_pingvin_points() -> None:
    service = SearchService(FakeSearchRepository())

    results = await service.search_people(
        SearchQuery(
            exclude_courses=SearchFilterList(ids=[20], conjunction=False),
            pingvin_points_above=0,
        )
    )

    assert [result.person_id for result in results] == [3]
