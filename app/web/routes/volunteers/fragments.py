from __future__ import annotations

from fastapi import APIRouter, Depends, Request

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


def _to_checkbox_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() == "on"


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
    )
    total_count = None
    if not cursor:
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
    group_id: int | None = None,
    role_id: int | None = None,
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
