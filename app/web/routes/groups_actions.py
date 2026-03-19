from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status

from app.dependencies import get_groups_service, get_semester_transfer_service, get_volunteers_service, require_admin_user, require_group_manager
from app.services.groups import GroupDeleteBlockedError, GroupHistoryNotFoundError, GroupRoleDeleteBlockedError, GroupsService
from app.services.semester_transfer import SemesterTransferEntry, SemesterTransferService
from app.services.volunteers import (
    DuplicateRoleAssignmentError,
    InvalidRoleAssignmentError,
    VolunteerNotFoundError,
    VolunteersService,
)
from app.web.route_helpers import blocked_http_exception, log_and_redirect
from app.web.templates import templates

router = APIRouter()


@router.post("/groups")
async def groups_create(
    request: Request,
    name: str = Form(...),
    description: str | None = Form(default=None),
    active_until_semester: int = Form(...),
    parent_group_id: str | None = Form(default=None),
    discount_step: str | None = Form(default=None),
    active: str | None = Form(default=None),
    current_user=Depends(require_admin_user),
    groups_service: GroupsService = Depends(get_groups_service),
):
    group_id = await groups_service.create_group(
        name=name,
        description=description,
        active=active == "true",
        active_until_semester=active_until_semester,
        parent_group_id=int(parent_group_id) if parent_group_id and parent_group_id.strip() else None,
        discount_step=int(discount_step) if discount_step and discount_step.strip() else None,
    )
    return log_and_redirect(
        request=request,
        user=current_user,
        action="group.create",
        subject_type="group",
        subject_id=group_id,
        redirect_path=f"/groups/{group_id}",
    )


@router.patch("/groups/{group_id}")
async def groups_update(
    request: Request,
    group_id: int,
    name: str = Form(...),
    description: str | None = Form(default=None),
    active_until_semester: int = Form(...),
    parent_group_id: str | None = Form(default=None),
    discount_step: str | None = Form(default=None),
    active: str | None = Form(default=None),
    current_user=Depends(require_group_manager),
    groups_service: GroupsService = Depends(get_groups_service),
):
    updated = await groups_service.update_group(
        group_id,
        name=name,
        description=description,
        active=active == "true",
        active_until_semester=active_until_semester,
        parent_group_id=(
            int(parent_group_id) if parent_group_id and parent_group_id.strip() and int(parent_group_id) != group_id else None
        ),
        discount_step=int(discount_step) if discount_step and discount_step.strip() else None,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    return log_and_redirect(
        request=request,
        user=current_user,
        action="group.update",
        subject_type="group",
        subject_id=group_id,
        redirect_path=f"/groups/{group_id}",
    )


@router.delete("/groups/{group_id}")
async def groups_delete(
    request: Request,
    group_id: int,
    current_user=Depends(require_admin_user),
    groups_service: GroupsService = Depends(get_groups_service),
):
    try:
        deleted = await groups_service.delete_group(group_id)
    except GroupDeleteBlockedError as exc:
        raise blocked_http_exception(exc.blockers) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    return log_and_redirect(
        request=request,
        user=current_user,
        action="group.delete",
        subject_type="group",
        subject_id=group_id,
        redirect_path="/groups",
    )


@router.post("/groups/{group_id}/roles")
async def group_roles_create(
    request: Request,
    group_id: int,
    role_name: str = Form(...),
    pingvin_points: int = Form(...),
    current_user=Depends(require_group_manager),
    groups_service: GroupsService = Depends(get_groups_service),
):
    role_id = await groups_service.create_group_role(
        group_id,
        role_name=role_name,
        pingvin_points=pingvin_points,
    )
    if role_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    return log_and_redirect(
        request=request,
        user=current_user,
        action="group_role.create",
        subject_type="group_role",
        subject_id=role_id,
        details={"group_id": group_id},
        redirect_path=f"/groups/{group_id}",
    )


@router.post("/groups/{group_id}/role-assignments")
async def group_role_assignments_create(
    request: Request,
    group_id: int,
    volunteer_id: int = Form(...),
    role_id: int = Form(...),
    year: int = Form(...),
    term: int = Form(...),
    contract_signed: bool = Form(default=False),
    current_user=Depends(require_group_manager),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    try:
        await volunteers_service.add_role_assignment(
            volunteer_id=volunteer_id,
            group_id=group_id,
            role_id=role_id,
            year=year,
            term=term,
            contract_signed=contract_signed,
        )
    except VolunteerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (DuplicateRoleAssignmentError, InvalidRoleAssignmentError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return log_and_redirect(
        request=request,
        user=current_user,
        action="group_role_assignment.create",
        subject_type="group",
        subject_id=group_id,
        details={"volunteer_id": volunteer_id, "role_id": role_id, "year": year, "term": term},
        redirect_path=f"/groups/{group_id}",
    )


@router.patch("/groups/{group_id}/roles/{role_id}")
async def group_roles_update(
    request: Request,
    group_id: int,
    role_id: int,
    role_name: str = Form(...),
    pingvin_points: int = Form(...),
    current_user=Depends(require_group_manager),
    groups_service: GroupsService = Depends(get_groups_service),
):
    updated = await groups_service.update_group_role(
        group_id,
        role_id,
        role_name=role_name,
        pingvin_points=pingvin_points,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group role not found.")
    return log_and_redirect(
        request=request,
        user=current_user,
        action="group_role.update",
        subject_type="group_role",
        subject_id=role_id,
        details={"group_id": group_id},
        redirect_path=f"/groups/{group_id}",
    )


@router.delete("/groups/{group_id}/roles/{role_id}")
async def group_roles_delete(
    request: Request,
    group_id: int,
    role_id: int,
    current_user=Depends(require_group_manager),
    groups_service: GroupsService = Depends(get_groups_service),
):
    try:
        deleted = await groups_service.delete_group_role(group_id, role_id)
    except GroupRoleDeleteBlockedError as exc:
        raise blocked_http_exception(exc.blockers) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group role not found.")
    return log_and_redirect(
        request=request,
        user=current_user,
        action="group_role.delete",
        subject_type="group_role",
        subject_id=role_id,
        details={"group_id": group_id},
        redirect_path=f"/groups/{group_id}",
    )


@router.delete("/groups/{group_id}/history/{history_id}")
async def group_history_delete(
    request: Request,
    group_id: int,
    history_id: int,
    current_user=Depends(require_group_manager),
    groups_service: GroupsService = Depends(get_groups_service),
):
    try:
        await groups_service.delete_group_history_entry(group_id, history_id)
    except GroupHistoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if request.headers.get("HX-Request") == "true":
        group = await groups_service.get_group_detail(group_id)
        if group is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
        history, stats, retention = await asyncio.gather(
            groups_service.get_group_history_by_semester(group_id),
            groups_service.get_group_semester_stats(group_id),
            groups_service.get_group_retention_stats(group_id),
        )
        return templates.TemplateResponse(
            request,
            "components/group_history_delete_oob.html",
            {
                "current_user": current_user,
                "group": group,
                "group_id": group_id,
                "history": history,
                "stats": stats,
                "retention": retention,
                "can_manage_group": True,
                "swap_oob": True,
            },
        )
    return log_and_redirect(
        request=request,
        user=current_user,
        action="group_history.delete",
        subject_type="role_assignment",
        subject_id=history_id,
        details={"group_id": group_id},
        redirect_path=f"/groups/{group_id}",
    )


@router.post("/groups/{group_id}/semester-transfer")
async def groups_apply_semester_transfer(
    request: Request,
    group_id: int,
    target_semester: int = Form(...),
    volunteer_ids: list[int] = Form(default=[]),
    role_ids: list[str] = Form(default=[]),
    current_user=Depends(require_group_manager),
    transfer_service: SemesterTransferService = Depends(get_semester_transfer_service),
):
    entries = [
        SemesterTransferEntry(
            volunteer_id=volunteer_id,
            role_id=(int(role_ids[index]) if index < len(role_ids) and role_ids[index].strip() else None),
        )
        for index, volunteer_id in enumerate(volunteer_ids)
    ]
    await transfer_service.apply_transfer(
        group_id=group_id,
        target_semester=target_semester,
        entries=entries,
    )
    return log_and_redirect(
        request=request,
        user=current_user,
        action="group.apply_semester_transfer",
        subject_type="group",
        subject_id=group_id,
        details={"target_semester": target_semester, "entry_count": len(entries)},
        redirect_path=f"/groups/{group_id}",
    )
