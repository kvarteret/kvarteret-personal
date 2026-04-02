from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.roles import UserRole
from app.dependencies import (
    get_groups_service,
    get_volunteers_service,
    require_authenticated_user,
)
from app.errors import NotConfiguredError
from app.observability import log_admin_activity
from app.domain.groups.service import GroupsService
from app.domain.volunteers.options import GENDER_OPTIONS
from app.domain.volunteers.service import VolunteersService
from app.web.templates import templates

router = APIRouter()
VOLUNTEERS_PAGE_SIZE = 20


@router.get("/volunteers/stats")
async def volunteers_stats(
    request: Request,
    current_user=Depends(require_authenticated_user),
    groups_service: GroupsService = Depends(get_groups_service),
):
    try:
        org_stats, group_counts, org_retention = await asyncio.gather(
            groups_service.get_org_stats_detailed(),
            groups_service.get_current_group_member_counts(),
            groups_service.get_org_retention_stats(),
        )
    except NotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed volunteer statistics are not configured yet.",
        )
    return templates.TemplateResponse(
        request,
        "pages/volunteers/volunteer_stats.html",
        {
            "title": "Organisasjonsstatistikk",
            "section": "volunteers",
            "current_user": current_user,
            "org_stats": org_stats,
            "group_counts": group_counts,
            "org_retention": org_retention,
        },
    )


@router.get("/volunteers")
async def volunteers_index(
    request: Request,
    q: str | None = None,
    cursor: str | None = None,
    current_user=Depends(require_authenticated_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    try:
        page = await volunteers_service.list_volunteers_page(query=q, limit=VOLUNTEERS_PAGE_SIZE, cursor=cursor)
    except NotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed volunteer views are not configured yet.",
        )
    return templates.TemplateResponse(
        request,
        "pages/volunteers/volunteers_index.html",
        {
            "title": "Volunteers",
            "section": "volunteers",
            "current_user": current_user,
            "volunteers": page.items,
            "query": q or "",
            "cursor": cursor,
            "next_cursor": page.next_cursor,
        },
    )


@router.get("/volunteers/{volunteer_id}")
async def volunteer_detail(
    request: Request,
    volunteer_id: int,
    current_user=Depends(require_authenticated_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    try:
        volunteer = await volunteers_service.get_volunteer_detail(volunteer_id)
    except NotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed volunteer views are not configured yet.",
        )
    if volunteer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Volunteer not found.")
    can_manage_profile = current_user.role in {UserRole.ADMIN, UserRole.GROUP_ADMIN}
    can_manage_photo = can_manage_profile
    if current_user.role == UserRole.ADMIN:
        log_admin_activity(
            request=request,
            user=current_user,
            action="volunteer.view_detail",
            subject_type="volunteer",
            subject_id=volunteer_id,
        )
    response = templates.TemplateResponse(
        request,
        "pages/volunteers/volunteer_detail.html",
        {
            "title": volunteer.full_name,
            "section": "volunteers",
            "current_user": current_user,
            "volunteer": volunteer,
            "can_manage_volunteer_profile": can_manage_profile,
            "can_manage_volunteer_photo": can_manage_photo,
            "gender_options": GENDER_OPTIONS,
            "duplicate_application_id": request.query_params.get("duplicate_application_id"),
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response
