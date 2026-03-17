from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.cache import TTLCache
from app.dependencies import get_courses_service, get_groups_service, require_authenticated_user
from app.services.courses import CoursesService
from app.services.groups import GroupsService
from app.web.templates import templates

router = APIRouter()
_GROUP_OPTIONS_CACHE: TTLCache[str, list] = TTLCache(ttl_seconds=300, max_entries=4)
_COURSE_OPTIONS_CACHE: TTLCache[str, list] = TTLCache(ttl_seconds=300, max_entries=4)


@router.get("/volunteers/search/options/groups")
async def volunteer_search_group_options(
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


@router.get("/volunteers/search/options/courses")
async def volunteer_search_course_options(
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


def _parse_selected_ids(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(item) for item in value.split(",") if item.strip()]
