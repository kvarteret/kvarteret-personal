from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_volunteers_service, require_admin_user, require_authenticated_user
from app.services.semester import get_current_semester_code
from app.services.volunteer_options import SEMESTER_TERM_OPTIONS
from app.services.volunteers import VolunteersService
from app.web.routes.volunteer_route_helpers import render_role_assignments_panel, require_existing_volunteer
from app.web.templates import templates

router = APIRouter()


@router.get("/volunteers/list")
async def volunteers_results(
    request: Request,
    q: str | None = None,
    cursor: str | None = None,
    current_user=Depends(require_authenticated_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    page = await volunteers_service.list_volunteers_page(query=q, limit=20, cursor=cursor)
    return templates.TemplateResponse(
        request,
        "components/volunteer_results.html",
        {
            "current_user": current_user,
            "volunteers": page.items,
            "query": q or "",
            "cursor": cursor,
            "next_cursor": page.next_cursor,
        },
    )


@router.get("/volunteers/{volunteer_id}/role-assignments/panel")
async def volunteer_role_assignments_panel(
    request: Request,
    volunteer_id: int,
    current_user=Depends(require_authenticated_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    volunteer = await require_existing_volunteer(volunteers_service, volunteer_id)
    return await render_role_assignments_panel(
        request,
        current_user=current_user,
        volunteers_service=volunteers_service,
        volunteer=volunteer,
    )


@router.get("/volunteers/{volunteer_id}/role-assignments/role-field")
async def volunteer_role_assignment_role_field(
    request: Request,
    volunteer_id: int,
    group_id: int | None = None,
    current_user=Depends(require_admin_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    volunteer = await require_existing_volunteer(volunteers_service, volunteer_id)
    groups = await volunteers_service.list_assignment_groups()
    selected_group_id = group_id if group_id is not None else None
    roles = await volunteers_service.list_assignment_roles(selected_group_id) if selected_group_id is not None else []
    return templates.TemplateResponse(
        request,
        "components/volunteer_role_assignment_form_fields.html",
        {
            "current_user": current_user,
            "volunteer": volunteer,
            "group_options": groups,
            "selected_group_id": selected_group_id,
            "role_options": roles,
            "semester_term_options": SEMESTER_TERM_OPTIONS,
            "default_year": get_current_semester_code() // 10,
            "default_term": get_current_semester_code() % 10,
        },
    )


@router.get("/volunteers/{volunteer_id}/documents/panel")
async def volunteer_documents_panel(
    request: Request,
    volunteer_id: int,
    current_user=Depends(require_authenticated_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    volunteer = await require_existing_volunteer(volunteers_service, volunteer_id)
    documents = await volunteers_service.list_volunteer_documents(volunteer_id)
    return templates.TemplateResponse(
        request,
        "components/volunteer_documents_panel.html",
        {
            "current_user": current_user,
            "volunteer": volunteer,
            "documents": documents,
        },
    )


@router.get("/volunteers/{volunteer_id}/relations/panel")
async def volunteer_relations_panel(
    request: Request,
    volunteer_id: int,
    current_user=Depends(require_authenticated_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    volunteer = await require_existing_volunteer(volunteers_service, volunteer_id)
    relations = await volunteers_service.get_volunteer_relations(volunteer_id)
    return templates.TemplateResponse(
        request,
        "components/volunteer_relations_panel.html",
        {
            "current_user": current_user,
            "volunteer": volunteer,
            "cards": relations.cards,
            "next_of_kin": relations.next_of_kin,
        },
    )
