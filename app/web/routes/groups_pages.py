from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_groups_service, get_semester_transfer_service, require_admin_user, require_authenticated_user
from app.errors import NotConfiguredError
from app.observability import log_admin_activity
from app.services.groups import GroupsService
from app.services.semester import get_current_semester_code
from app.services.semester_transfer import SemesterTransferService
from app.web.route_helpers import not_configured_http_exception
from app.web.templates import templates

router = APIRouter()


@router.get("/groups")
async def groups_index(
    request: Request,
    q: str | None = None,
    current_user=Depends(require_authenticated_user),
    groups_service: GroupsService = Depends(get_groups_service),
):
    try:
        groups = await groups_service.list_groups(query=q, limit=100)
    except NotConfiguredError:
        raise not_configured_http_exception("Database-backed group views are not configured yet.")
    return templates.TemplateResponse(
        request,
        "pages/groups.html",
        {
            "title": "Groups",
            "section": "groups",
            "current_user": current_user,
            "groups": groups,
            "query": q or "",
        },
    )


@router.get("/groups/new")
async def groups_new(
    request: Request,
    current_user=Depends(require_admin_user),
    groups_service: GroupsService = Depends(get_groups_service),
):
    try:
        group_options = await groups_service.list_groups(limit=500)
    except NotConfiguredError:
        raise not_configured_http_exception("Database-backed group views are not configured yet.")
    return templates.TemplateResponse(
        request,
        "pages/group_new.html",
        {
            "title": "Ny gruppe",
            "section": "groups",
            "current_user": current_user,
            "group_options": group_options,
            "default_group_active_until": get_current_semester_code(),
        },
    )


@router.get("/groups/{group_id}")
async def groups_detail(
    request: Request,
    group_id: int,
    current_user=Depends(require_authenticated_user),
    groups_service: GroupsService = Depends(get_groups_service),
):
    try:
        group = await groups_service.get_group_detail(group_id)
        group_options = await groups_service.list_groups(limit=500)
    except NotConfiguredError:
        raise not_configured_http_exception("Database-backed group views are not configured yet.")
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    return templates.TemplateResponse(
        request,
        "pages/group_detail.html",
        {
            "title": group.name,
            "section": "groups",
            "current_user": current_user,
            "group": group,
            "group_options": [option for option in group_options if option.group_id != group.group_id],
        },
    )


@router.get("/groups/{group_id}/history")
async def groups_detail_history(
    request: Request,
    group_id: int,
    current_user=Depends(require_authenticated_user),
    groups_service: GroupsService = Depends(get_groups_service),
):
    try:
        history = await groups_service.get_group_history_by_semester(group_id)
    except NotConfiguredError:
        raise not_configured_http_exception("Database-backed group views are not configured yet.")
    return templates.TemplateResponse(
        request,
        "components/group_history.html",
        {"current_user": current_user, "history": history, "group_id": group_id},
    )


@router.get("/groups/{group_id}/stats")
async def groups_detail_stats(
    request: Request,
    group_id: int,
    current_user=Depends(require_authenticated_user),
    groups_service: GroupsService = Depends(get_groups_service),
):
    try:
        stats, retention = await asyncio.gather(
            groups_service.get_group_semester_stats(group_id),
            groups_service.get_group_retention_stats(group_id),
        )
    except NotConfiguredError:
        raise not_configured_http_exception("Database-backed group views are not configured yet.")
    return templates.TemplateResponse(
        request,
        "components/group_stats.html",
        {"current_user": current_user, "stats": stats, "retention": retention},
    )


@router.get("/groups/{group_id}/semester-transfer")
async def groups_semester_transfer(
    request: Request,
    group_id: int,
    source_semester: int | None = None,
    target_semester: int | None = None,
    current_user=Depends(require_admin_user),
    transfer_service: SemesterTransferService = Depends(get_semester_transfer_service),
):
    preview = await transfer_service.preview_transfer(
        group_id=group_id,
        source_semester=source_semester,
        target_semester=target_semester,
    )
    log_admin_activity(
        request=request,
        user=current_user,
        action="group.preview_semester_transfer",
        subject_type="group",
        subject_id=group_id,
        details={"source_semester": preview.source_semester, "target_semester": preview.target_semester},
    )
    return templates.TemplateResponse(
        request,
        "pages/semester_transfer.html",
        {
            "title": f"Flytt til nytt semester · {preview.group_name}",
            "section": "groups",
            "current_user": current_user,
            "preview": preview,
        },
    )
