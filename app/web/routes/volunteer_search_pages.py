from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from app.auth.roles import UserRole
from app.dependencies import get_volunteer_search_service, require_authenticated_user
from app.observability import log_admin_activity
from app.services.search import SearchFilterList, SearchQuery, VolunteerSearchService
from app.web.templates import templates

router = APIRouter()


@router.get("/volunteers/search")
async def search_volunteers_page(
    request: Request,
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
    current_user=Depends(require_authenticated_user),
    volunteer_search_service: VolunteerSearchService = Depends(get_volunteer_search_service),
):
    pingvin_points_above_value = _to_optional_int(pingvin_points_above)
    pingvin_points_below_value = _to_optional_int(pingvin_points_below)
    has_active_signed_contract_enabled = _to_checkbox_bool(has_active_signed_contract)
    should_run_search = bool(request.query_params)

    results = []
    if should_run_search:
        results = await volunteer_search_service.search_volunteers(
            SearchQuery(
                birth_date_after=date.fromisoformat(birth_date_after) if birth_date_after else None,
                birth_date_before=date.fromisoformat(birth_date_before) if birth_date_before else None,
                pingvin_points_above=pingvin_points_above_value,
                pingvin_points_below=pingvin_points_below_value,
                has_active_signed_contract=has_active_signed_contract_enabled,
                include_groups=_to_filter_list(include_groups),
                include_current_groups=_to_filter_list(include_current_groups),
                exclude_groups=_to_filter_list(exclude_groups),
                exclude_current_groups=_to_filter_list(exclude_current_groups),
                include_courses=_to_filter_list(include_courses),
                exclude_courses=_to_filter_list(exclude_courses),
            )
        )
        if current_user.role == UserRole.ADMIN:
            log_admin_activity(
                request=request,
                user=current_user,
                action="search.volunteers",
                subject_type="volunteer",
                details={
                    "result_count": len(results),
                    "include_groups": include_groups,
                    "include_current_groups": include_current_groups,
                    "exclude_groups": exclude_groups,
                    "exclude_current_groups": exclude_current_groups,
                    "include_courses": include_courses,
                    "exclude_courses": exclude_courses,
                    "birth_date_after": birth_date_after or "",
                    "birth_date_before": birth_date_before or "",
                    "pingvin_points_above": pingvin_points_above_value,
                    "pingvin_points_below": pingvin_points_below_value,
                    "has_active_signed_contract": has_active_signed_contract_enabled,
                },
            )

    return templates.TemplateResponse(
        request,
        "pages/volunteers_search.html",
        {
            "title": "Volunteer Search",
            "section": "volunteer-search",
            "current_user": current_user,
            "results": results,
            "form": {
                "birth_date_after": birth_date_after or "",
                "birth_date_before": birth_date_before or "",
                "pingvin_points_above": pingvin_points_above_value or "",
                "pingvin_points_below": pingvin_points_below_value or "",
                "has_active_signed_contract": has_active_signed_contract_enabled,
                "include_groups": include_groups,
                "include_current_groups": include_current_groups,
                "exclude_groups": exclude_groups,
                "exclude_current_groups": exclude_current_groups,
                "include_courses": include_courses,
                "exclude_courses": exclude_courses,
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
