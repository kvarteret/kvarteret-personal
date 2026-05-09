from __future__ import annotations

from time import monotonic

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.dependencies import get_volunteers_service
from app.domain.volunteers.service import VolunteersService

router = APIRouter()

_CACHE_TTL = 24 * 3600
_cached_stats: dict | None = None
_cache_expires_at: float = 0.0


class VolunteerStatsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    totalVolunteers: int
    currentSemesterVolunteers: int


_RESPONSE_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": "public, max-age=3600",
}


@router.get(
    "",
    response_model=VolunteerStatsResponse,
    operation_id="getVolunteerStats",
)
async def get_volunteer_stats(
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
) -> JSONResponse:
    global _cached_stats, _cache_expires_at

    now = monotonic()
    if _cached_stats is not None and now < _cache_expires_at:
        return JSONResponse(content=_cached_stats, headers=_RESPONSE_HEADERS)

    total, current = await _fetch_counts(volunteers_service)
    _cached_stats = {"totalVolunteers": total, "currentSemesterVolunteers": current}
    _cache_expires_at = now + _CACHE_TTL

    return JSONResponse(content=_cached_stats, headers=_RESPONSE_HEADERS)


async def _fetch_counts(service: VolunteersService) -> tuple[int, int]:
    total = await service.count_volunteers()
    current = await service.count_volunteers(only_active=True)
    return total, current
