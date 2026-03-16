from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.cache import TTLCache
from app.dependencies import get_courses_service, get_groups_service, get_search_service, require_authenticated_user
from app.observability import log_admin_activity
from app.auth.roles import UserRole
from app.services.courses import CoursesService
from app.services.groups import GroupsService
from app.services.search import SearchFilterList, SearchQuery, SearchService
from app.web.templates import templates

router = APIRouter()
_GROUP_OPTIONS_CACHE: TTLCache[str, list] = TTLCache(ttl_seconds=300, max_entries=4)
_COURSE_OPTIONS_CACHE: TTLCache[str, list] = TTLCache(ttl_seconds=300, max_entries=4)


@router.get("/search")
async def search_people_page(
    request: Request,
    birth_date_after: str | None = None,
    birth_date_before: str | None = None,
    pingvin_points_above: int | None = None,
    pingvin_points_below: int | None = None,
    include_groups: list[int] = Query(default_factory=list),
    include_current_groups: list[int] = Query(default_factory=list),
    exclude_groups: list[int] = Query(default_factory=list),
    exclude_current_groups: list[int] = Query(default_factory=list),
    include_courses: list[int] = Query(default_factory=list),
    exclude_courses: list[int] = Query(default_factory=list),
    current_user=Depends(require_authenticated_user),
    search_service: SearchService = Depends(get_search_service),
):
    results = []
    if any(
        value not in (None, "", [])
        for value in [
            birth_date_after,
            birth_date_before,
            pingvin_points_above,
            pingvin_points_below,
            include_groups,
            include_current_groups,
            exclude_groups,
            exclude_current_groups,
            include_courses,
            exclude_courses,
        ]
    ):
        results = await search_service.search_people(
            SearchQuery(
                birth_date_after=date.fromisoformat(birth_date_after) if birth_date_after else None,
                birth_date_before=date.fromisoformat(birth_date_before) if birth_date_before else None,
                pingvin_points_above=pingvin_points_above,
                pingvin_points_below=pingvin_points_below,
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
                action="search.people",
                subject_type="person",
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
                    "pingvin_points_above": pingvin_points_above,
                    "pingvin_points_below": pingvin_points_below,
                },
            )

    return templates.TemplateResponse(
        request,
        "pages/search.html",
        {
            "title": "Search",
            "section": "search",
            "current_user": current_user,
            "results": results,
            "form": {
                "birth_date_after": birth_date_after or "",
                "birth_date_before": birth_date_before or "",
                "pingvin_points_above": pingvin_points_above or "",
                "pingvin_points_below": pingvin_points_below or "",
                "include_groups": include_groups,
                "include_current_groups": include_current_groups,
                "exclude_groups": exclude_groups,
                "exclude_current_groups": exclude_current_groups,
                "include_courses": include_courses,
                "exclude_courses": exclude_courses,
            },
        },
    )


@router.get("/search/options/groups")
async def search_group_options(
    request: Request,
    field: str,
    selected: str | None = None,
    current_user=Depends(require_authenticated_user),
    groups_service: GroupsService = Depends(get_groups_service),
):
    labels = {
        "include_groups": "Inkluder grupper",
        "include_current_groups": "Inkluder aktive grupper",
        "exclude_groups": "Ekskluder grupper",
        "exclude_current_groups": "Ekskluder aktive grupper",
    }
    if field not in labels:
        return Response(status_code=400)
    groups = _GROUP_OPTIONS_CACHE.get("all")
    if groups is None:
        groups = await groups_service.list_groups(limit=200)
        _GROUP_OPTIONS_CACHE.set("all", groups)
    return templates.TemplateResponse(
        request,
        "components/search_filter_select.html",
        {
            "current_user": current_user,
            "field": field,
            "label": labels[field],
            "options": groups,
            "selected_ids": _parse_selected_ids(selected),
            "value_attr": "group_id",
            "label_attr": "name",
        },
    )


@router.get("/search/options/courses")
async def search_course_options(
    request: Request,
    field: str,
    selected: str | None = None,
    current_user=Depends(require_authenticated_user),
    courses_service: CoursesService = Depends(get_courses_service),
):
    labels = {
        "include_courses": "Inkluder kurs",
        "exclude_courses": "Ekskluder kurs",
    }
    if field not in labels:
        return Response(status_code=400)
    courses = _COURSE_OPTIONS_CACHE.get("all")
    if courses is None:
        courses = await courses_service.list_courses(limit=200)
        _COURSE_OPTIONS_CACHE.set("all", courses)
    return templates.TemplateResponse(
        request,
        "components/search_filter_select.html",
        {
            "current_user": current_user,
            "field": field,
            "label": labels[field],
            "options": courses,
            "selected_ids": _parse_selected_ids(selected),
            "value_attr": "course_id",
            "label_attr": "name",
        },
    )


def _to_filter_list(values: list[int]) -> SearchFilterList | None:
    if not values:
        return None
    return SearchFilterList(ids=values)


def _parse_selected_ids(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(item) for item in value.split(",") if item.strip()]
