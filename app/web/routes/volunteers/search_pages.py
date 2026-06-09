from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from app.auth.roles import UserRole
from app.dependencies import get_volunteer_search_service, require_authenticated_user
from app.observability import log_admin_activity
from app.domain.search import SearchFilterList, SearchQuery, VolunteerSearchService
from app.web.templates import templates

router = APIRouter()


async def _parse_search_filters(
    birth_date_after: str | None = None,
    birth_date_before: str | None = None,
    pingvin_points_above: str | None = None,
    pingvin_points_below: str | None = None,
    has_active_signed_contract: str | None = None,
    include_groups: list[int] = Query(default_factory=list),
    include_current_groups: list[int] = Query(default_factory=list),
    exclude_groups: list[int] = Query(default_factory=list),
    exclude_current_groups: list[int] = Query(default_factory=list),
    include_courses: list[int] = Query(default_factory=list),
    exclude_courses: list[int] = Query(default_factory=list),
) -> SearchQuery:
    return SearchQuery(
        birth_date_after=date.fromisoformat(birth_date_after)
        if birth_date_after
        else None,
        birth_date_before=date.fromisoformat(birth_date_before)
        if birth_date_before
        else None,
        pingvin_points_above=_to_optional_int(pingvin_points_above),
        pingvin_points_below=_to_optional_int(pingvin_points_below),
        has_active_signed_contract=_to_checkbox_bool(has_active_signed_contract),
        include_groups=_to_filter_list(include_groups),
        include_current_groups=_to_filter_list(include_current_groups),
        exclude_groups=_to_filter_list(exclude_groups),
        exclude_current_groups=_to_filter_list(exclude_current_groups),
        include_courses=_to_filter_list(include_courses),
        exclude_courses=_to_filter_list(exclude_courses),
    )


@router.get("/volunteers/search")
async def search_volunteers_page(
    request: Request,
    search_filters: SearchQuery = Depends(_parse_search_filters),
    current_user=Depends(require_authenticated_user),
    volunteer_search_service: VolunteerSearchService = Depends(
        get_volunteer_search_service
    ),
):
    should_run_search = bool(request.query_params)
    params = request.query_params

    results = []
    if should_run_search:
        results = await volunteer_search_service.search_volunteers(search_filters)
        if current_user.role == UserRole.ADMIN:
            log_admin_activity(
                request=request,
                user=current_user,
                action="search.volunteers",
                subject_type="volunteer",
                details={
                    "result_count": len(results),
                    "include_groups": search_filters.include_groups,
                    "include_current_groups": search_filters.include_current_groups,
                    "exclude_groups": search_filters.exclude_groups,
                    "exclude_current_groups": search_filters.exclude_current_groups,
                    "include_courses": search_filters.include_courses,
                    "exclude_courses": search_filters.exclude_courses,
                    "birth_date_after": params.get("birth_date_after", ""),
                    "birth_date_before": params.get("birth_date_before", ""),
                    "pingvin_points_above": search_filters.pingvin_points_above,
                    "pingvin_points_below": search_filters.pingvin_points_below,
                    "has_active_signed_contract": search_filters.has_active_signed_contract,
                },
            )

    return templates.TemplateResponse(
        request,
        "pages/volunteers/volunteers_search.html",
        {
            "title": "Volunteer Search",
            "section": "volunteer-search",
            "current_user": current_user,
            "results": results,
            "form": {
                "birth_date_after": params.get("birth_date_after", ""),
                "birth_date_before": params.get("birth_date_before", ""),
                "pingvin_points_above": params.get("pingvin_points_above", ""),
                "pingvin_points_below": params.get("pingvin_points_below", ""),
                "has_active_signed_contract": params.get(
                    "has_active_signed_contract", False
                ),
                "include_groups": params.getlist("include_groups"),
                "include_current_groups": params.getlist("include_current_groups"),
                "exclude_groups": params.getlist("exclude_groups"),
                "exclude_current_groups": params.getlist("exclude_current_groups"),
                "include_courses": params.getlist("include_courses"),
                "exclude_courses": params.getlist("exclude_courses"),
            },
        },
    )


def _to_filter_list(values: list[int]) -> SearchFilterList | None:
    if not values:
        return None
    return SearchFilterList(ids=values)


def _to_checkbox_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() == "on"


def _to_optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return int(stripped)
