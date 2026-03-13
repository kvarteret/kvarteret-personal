from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.dependencies import get_groups_service, get_semester_transfer_service, require_authenticated_user, require_web_admin_user
from app.errors import NotConfiguredError
from app.observability import log_admin_activity
from app.services.groups import GroupsService
from app.services.semester_transfer import SemesterTransferEntry, SemesterTransferService
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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed group views are not configured yet.",
        )
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


@router.get("/groups/{group_id}")
async def groups_detail(
    request: Request,
    group_id: int,
    current_user=Depends(require_authenticated_user),
    groups_service: GroupsService = Depends(get_groups_service),
):
    try:
        group = await groups_service.get_group_detail(group_id)
    except NotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed group views are not configured yet.",
        )
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
        },
    )


@router.get("/groups/{group_id}/semester-transfer")
async def groups_semester_transfer(
    request: Request,
    group_id: int,
    source_semester: int | None = None,
    target_semester: int | None = None,
    current_user=Depends(require_web_admin_user),
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
            "title": f"Semester transfer · {preview.group_name}",
            "section": "groups",
            "current_user": current_user,
            "preview": preview,
        },
    )


@router.post("/groups/{group_id}/semester-transfer")
async def groups_apply_semester_transfer(
    request: Request,
    group_id: int,
    target_semester: int = Form(...),
    person_ids: list[int] = Form(default=[]),
    role_ids: list[str] = Form(default=[]),
    current_user=Depends(require_web_admin_user),
    transfer_service: SemesterTransferService = Depends(get_semester_transfer_service),
):
    entries = [
        SemesterTransferEntry(
            person_id=person_id,
            role_id=(int(role_ids[index]) if index < len(role_ids) and role_ids[index].strip() else None),
        )
        for index, person_id in enumerate(person_ids)
    ]
    await transfer_service.apply_transfer(
        group_id=group_id,
        target_semester=target_semester,
        entries=entries,
    )
    log_admin_activity(
        request=request,
        user=current_user,
        action="group.apply_semester_transfer",
        subject_type="group",
        subject_id=group_id,
        details={"target_semester": target_semester, "entry_count": len(entries)},
    )
    return RedirectResponse(url=f"/groups/{group_id}", status_code=status.HTTP_303_SEE_OTHER)
