from __future__ import annotations

import json
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BeforeValidator

from app.dependencies import (
    get_courses_service,
    get_volunteers_service,
    require_authenticated_user,
    require_management_user,
)
from app.domain.courses.service import CoursesService
from app.shared.semester import get_current_semester_code
from app.domain.volunteers.options import SEMESTER_TERM_OPTIONS
from app.domain.volunteers.service import VolunteersService
from app.web.routes.volunteers.helpers import (
    render_course_completions_panel,
    render_relations_panel,
    render_role_assignments_panel,
    require_existing_volunteer,
)
from app.web.templates import templates

router = APIRouter()

OptionalSelection = Annotated[
    int | None, BeforeValidator(lambda value: None if value == "" else value)
]


def _to_checkbox_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() == "on"


PHOTO_URL_BATCH_LIMIT = 100


@router.get("/volunteers/search-index")
async def volunteers_search_index(
    request: Request,
    current_user=Depends(require_authenticated_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    """Compact index of every volunteer for instant, in-browser filtering."""
    body, etag = _encoded_search_index(await volunteers_service.get_search_index())
    # Personal data: never shared caches, and always revalidated so edits
    # show up; an unchanged index costs a 304 instead of the payload.
    headers = {"Cache-Control": "private, no-cache", "ETag": etag, "Vary": "Cookie"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


_encoded_index: tuple[dict, bytes, str] | None = None


def _encoded_search_index(index: dict) -> tuple[bytes, str]:
    # The service hands back the same cached dict until it rebuilds, so
    # encode and hash it once per build rather than per request. Holding the
    # dict (not its id) keeps a rebuilt index from matching a stale encoding.
    global _encoded_index
    if _encoded_index is None or _encoded_index[0] is not index:
        body = json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode()
        _encoded_index = (index, body, f'"{sha256(body).hexdigest()[:20]}"')
    return _encoded_index[1], _encoded_index[2]


@router.get("/volunteers/photo-urls")
async def volunteers_photo_urls(
    ids: str = "",
    current_user=Depends(require_authenticated_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    """Signed photo URLs for the rows the instant search is showing."""
    volunteer_ids = [
        int(part) for part in ids.split(",") if part.strip().isdigit()
    ][:PHOTO_URL_BATCH_LIMIT]
    urls = await volunteers_service.get_photo_urls(volunteer_ids)
    return JSONResponse(
        {str(volunteer_id): url for volunteer_id, url in urls.items()},
        headers={"Cache-Control": "private, max-age=600"},
    )


@router.get("/volunteers/list")
async def volunteers_results(
    request: Request,
    q: str | None = None,
    cursor: str | None = None,
    only_active: str | None = None,
    current_user=Depends(require_authenticated_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    only_active_bool = _to_checkbox_bool(only_active, default=True)
    page = await volunteers_service.list_volunteers_page(
        query=q,
        limit=20,
        cursor=cursor,
        only_active=only_active_bool,
        include_total=not cursor,
    )
    total_count = page.total_count
    if total_count is None and not cursor:
        total_count = await volunteers_service.count_volunteers(
            query=q, only_active=only_active_bool
        )
    return templates.TemplateResponse(
        request,
        "components/volunteers/volunteer_results.html",
        {
            "current_user": current_user,
            "volunteers": page.items,
            "query": q or "",
            "cursor": cursor,
            "next_cursor": page.next_cursor,
            "total_count": total_count,
            "only_active": only_active_bool,
        },
    )


@router.get("/volunteers/{volunteer_id}/role-assignments/panel")
async def volunteer_role_assignments_panel(
    request: Request,
    volunteer_id: int,
    edit_assignment_id: int | None = None,
    current_user=Depends(require_authenticated_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    volunteer = await require_existing_volunteer(volunteers_service, volunteer_id)
    return await render_role_assignments_panel(
        request,
        current_user=current_user,
        volunteers_service=volunteers_service,
        volunteer=volunteer,
        editing_assignment_id=edit_assignment_id,
    )


@router.get("/volunteers/{volunteer_id}/role-assignments/role-field")
async def volunteer_role_assignment_role_field(
    request: Request,
    volunteer_id: int,
    group_id: OptionalSelection = None,
    role_id: OptionalSelection = None,
    year: int | None = None,
    term: int | None = None,
    current_user=Depends(require_management_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    volunteer = await require_existing_volunteer(volunteers_service, volunteer_id)
    groups = await volunteers_service.list_assignment_groups()
    selected_group_id = group_id if group_id is not None else None
    roles = (
        await volunteers_service.list_assignment_roles(selected_group_id)
        if selected_group_id is not None
        else []
    )
    selected_role_id = next(
        (candidate.role_id for candidate in roles if candidate.role_id == role_id), None
    )
    current_semester_code = get_current_semester_code()
    return templates.TemplateResponse(
        request,
        "components/volunteers/volunteer_role_assignment_form_fields.html",
        {
            "current_user": current_user,
            "volunteer": volunteer,
            "group_options": groups,
            "selected_group_id": selected_group_id,
            "selected_role_id": selected_role_id,
            "role_options": roles,
            "semester_term_options": SEMESTER_TERM_OPTIONS,
            "default_year": year if year is not None else current_semester_code // 10,
            "default_term": term if term is not None else current_semester_code % 10,
        },
    )


@router.get("/volunteers/{volunteer_id}/course-completions/panel")
async def volunteer_course_completions_panel(
    request: Request,
    volunteer_id: int,
    current_user=Depends(require_authenticated_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
    courses_service: CoursesService = Depends(get_courses_service),
):
    volunteer = await require_existing_volunteer(volunteers_service, volunteer_id)
    return await render_course_completions_panel(
        request,
        current_user=current_user,
        volunteers_service=volunteers_service,
        courses_service=courses_service,
        volunteer=volunteer,
    )


@router.get("/volunteers/{volunteer_id}/relations/panel")
async def volunteer_relations_panel(
    request: Request,
    volunteer_id: int,
    edit: bool = False,
    current_user=Depends(require_authenticated_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    volunteer = await require_existing_volunteer(volunteers_service, volunteer_id)
    return await render_relations_panel(
        request,
        current_user=current_user,
        volunteers_service=volunteers_service,
        volunteer=volunteer,
        editing=edit,
    )
