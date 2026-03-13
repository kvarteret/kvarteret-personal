from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.errors import ApiErrorResponse
from app.auth.dependencies import require_authenticated_user
from app.services.search import SearchFilterList, SearchQuery, SearchService, SearchResultItem, get_search_service

router = APIRouter()


class SearchFilterListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[int] = Field(default_factory=list)
    conjunction: bool = False


class SearchPeopleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    birth_date_before: date | None = None
    birth_date_after: date | None = None
    pingvin_points_below: int | None = None
    pingvin_points_above: int | None = None
    include_groups: SearchFilterListRequest | None = None
    include_current_groups: SearchFilterListRequest | None = None
    exclude_groups: SearchFilterListRequest | None = None
    exclude_current_groups: SearchFilterListRequest | None = None
    include_courses: SearchFilterListRequest | None = None
    exclude_courses: SearchFilterListRequest | None = None


class SearchPersonResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

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


def _get_search_service_for_request(request: Request) -> SearchService:
    if getattr(request.app.state, "search_service", None) is not None:
        return request.app.state.search_service
    return get_search_service()


def _to_filter_list(value: SearchFilterListRequest | None) -> SearchFilterList | None:
    if value is None:
        return None
    return SearchFilterList(ids=value.ids, conjunction=value.conjunction)


@router.post(
    "/search/people",
    response_model=list[SearchPersonResultResponse],
    responses={503: {"model": ApiErrorResponse}},
)
async def search_people(
    request: Request,
    payload: SearchPeopleRequest,
    _current_user=Depends(require_authenticated_user),
):
    try:
        results = await _get_search_service_for_request(request).search_people(
            SearchQuery(
                birth_date_before=payload.birth_date_before,
                birth_date_after=payload.birth_date_after,
                pingvin_points_below=payload.pingvin_points_below,
                pingvin_points_above=payload.pingvin_points_above,
                include_groups=_to_filter_list(payload.include_groups),
                include_current_groups=_to_filter_list(payload.include_current_groups),
                exclude_groups=_to_filter_list(payload.exclude_groups),
                exclude_current_groups=_to_filter_list(payload.exclude_current_groups),
                include_courses=_to_filter_list(payload.include_courses),
                exclude_courses=_to_filter_list(payload.exclude_courses),
            )
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "search_unavailable", "message": str(exc)},
        ) from exc
    return [SearchPersonResultResponse.model_validate(result) for result in results]
