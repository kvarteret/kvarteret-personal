from __future__ import annotations

from datetime import date

import pytest

from app.services.search import SearchFilterList, SearchQuery, SearchResultItem, VolunteerSearchService


class FakeSearchRepository:
    def __init__(self) -> None:
        self.last_query = None

    async def search_volunteers(self, query: SearchQuery) -> list[SearchResultItem]:
        self.last_query = query
        return [
            SearchResultItem(
                volunteer_id=3,
                first_name="Third",
                last_name="Person",
                full_name="Third Person",
                pingvin_points=1,
                last_semester_code=20262,
                last_semester_label="Fall 2026",
                birth_date=date(1969, 12, 28),
                phone="3",
                email="person.three@example.test",
            )
        ]


@pytest.mark.asyncio
async def test_search_service_delegates_query_to_repository() -> None:
    repository = FakeSearchRepository()
    service = VolunteerSearchService(repository)
    query = SearchQuery(
        include_groups=SearchFilterList(ids=[10, 12], conjunction=False),
        pingvin_points_above=0,
    )

    results = await service.search_volunteers(query)

    assert [result.volunteer_id for result in results] == [3]
    assert repository.last_query == query
