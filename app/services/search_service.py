from __future__ import annotations

import logging
from time import perf_counter

from app.observability import log_operation_timing
from app.services.search_models import SearchQuery, SearchRepositoryProtocol, SearchResultItem

logger = logging.getLogger("app.performance")


class SearchService:
    def __init__(self, repository: SearchRepositoryProtocol) -> None:
        self.repository = repository

    async def search_people(self, query: SearchQuery) -> list[SearchResultItem]:
        started_at = perf_counter()
        try:
            return await self.repository.search_people(query)
        finally:
            log_operation_timing(logger, operation="search.execute", started_at=started_at)
