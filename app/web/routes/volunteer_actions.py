from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse

from app.dependencies import get_volunteers_service, require_management_user
from app.observability import log_admin_activity
from app.services.volunteers import (
    DuplicateRoleAssignmentError,
    DocumentNotFoundError,
    InvalidRoleAssignmentError,
    RoleAssignmentNotFoundError,
    UnsupportedUploadError,
    VolunteersService,
    VolunteerNotFoundError,
)
from app.web.routes.volunteer_route_helpers import render_role_assignments_panel, require_existing_volunteer

router = APIRouter()


@router.patch("/volunteers/{volunteer_id}")
async def volunteer_update_profile(
    request: Request,
    volunteer_id: int,
    first_name: str | None = Form(default=None),
    last_name: str = Form(...),
    email: str | None = Form(default=None),
    phone: str | None = Form(default=None),
    birth_date: str | None = Form(default=None),
    gender: str = Form(default="A"),
    address: str | None = Form(default=None),
    postal_code: str | None = Form(default=None),
    current_user=Depends(require_management_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    try:
        await volunteers_service.update_volunteer_profile(
            volunteer_id=volunteer_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            birth_date=date.fromisoformat(birth_date) if birth_date else None,
            gender_code=gender,
            address=address,
            postal_code=postal_code,
        )
    except VolunteerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer.update_profile",
        subject_type="volunteer",
        subject_id=volunteer_id,
    )
    return RedirectResponse(url=f"/volunteers/{volunteer_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/volunteers/{volunteer_id}/role-assignments")
async def volunteer_add_role_assignment(
    request: Request,
    volunteer_id: int,
    year: int = Form(...),
    term: int = Form(...),
    group_id: int = Form(...),
    role_id: int = Form(...),
    contract_signed: bool = Form(default=False),
    current_user=Depends(require_management_user),
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
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer.add_role_assignment",
        subject_type="volunteer",
        subject_id=volunteer_id,
        details={"group_id": group_id, "role_id": role_id, "year": year, "term": term},
    )
    if request.headers.get("HX-Request") == "true":
        volunteer = await require_existing_volunteer(volunteers_service, volunteer_id)
        return await render_role_assignments_panel(
            request,
            current_user=current_user,
            volunteers_service=volunteers_service,
            volunteer=volunteer,
        )
    return RedirectResponse(url=f"/volunteers/{volunteer_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.patch("/volunteers/{volunteer_id}/role-assignments/{assignment_id}")
async def volunteer_update_role_assignment(
    request: Request,
    volunteer_id: int,
    assignment_id: int,
    year: int = Form(...),
    term: int = Form(...),
    group_id: int = Form(...),
    role_id: int = Form(...),
    contract_signed: bool = Form(default=False),
    current_user=Depends(require_management_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    try:
        await volunteers_service.update_role_assignment_for_volunteer(
            volunteer_id,
            assignment_id,
            group_id=group_id,
            role_id=role_id,
            year=year,
            term=term,
            contract_signed=contract_signed,
        )
    except RoleAssignmentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (DuplicateRoleAssignmentError, InvalidRoleAssignmentError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer.update_role_assignment",
        subject_type="role_assignment",
        subject_id=assignment_id,
        details={"volunteer_id": volunteer_id, "group_id": group_id, "role_id": role_id, "year": year, "term": term},
    )
    if request.headers.get("HX-Request") == "true":
        volunteer = await require_existing_volunteer(volunteers_service, volunteer_id)
        return await render_role_assignments_panel(
            request,
            current_user=current_user,
            volunteers_service=volunteers_service,
            volunteer=volunteer,
        )
    return RedirectResponse(url=f"/volunteers/{volunteer_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.delete("/volunteers/{volunteer_id}/role-assignments/{assignment_id}")
async def volunteer_delete_role_assignment(
    request: Request,
    volunteer_id: int,
    assignment_id: int,
    current_user=Depends(require_management_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    try:
        await volunteers_service.delete_role_assignment_for_volunteer(volunteer_id, assignment_id)
    except RoleAssignmentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer.delete_role_assignment",
        subject_type="role_assignment",
        subject_id=assignment_id,
        details={"volunteer_id": volunteer_id},
    )
    if request.headers.get("HX-Request") == "true":
        volunteer = await require_existing_volunteer(volunteers_service, volunteer_id)
        return await render_role_assignments_panel(
            request,
            current_user=current_user,
            volunteers_service=volunteers_service,
            volunteer=volunteer,
        )
    return RedirectResponse(url=f"/volunteers/{volunteer_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.delete("/volunteers/{volunteer_id}/photo")
@router.post("/volunteers/{volunteer_id}/photo")
async def volunteer_upload_photo(
    request: Request,
    volunteer_id: int,
    photo: UploadFile = File(...),
    current_user=Depends(require_management_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    try:
        if not photo.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a photo to upload.")
        await volunteers_service.upload_photo(
            volunteer_id=volunteer_id,
            filename=photo.filename,
            content=await photo.read(),
            content_type=photo.content_type,
        )
    except VolunteerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UnsupportedUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        await photo.close()
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer.upload_photo",
        subject_type="volunteer",
        subject_id=volunteer_id,
    )
    return RedirectResponse(url=f"/volunteers/{volunteer_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.delete("/volunteers/{volunteer_id}/photo")
async def volunteer_delete_photo(
    request: Request,
    volunteer_id: int,
    current_user=Depends(require_management_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    try:
        await volunteers_service.delete_photo(volunteer_id)
    except VolunteerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer.delete_photo",
        subject_type="volunteer",
        subject_id=volunteer_id,
    )
    return RedirectResponse(url=f"/volunteers/{volunteer_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.delete("/volunteers/{volunteer_id}/documents/{document_id}")
async def volunteer_delete_document(
    request: Request,
    volunteer_id: int,
    document_id: int,
    current_user=Depends(require_management_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    try:
        await volunteers_service.delete_document_for_volunteer(volunteer_id, document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer.delete_document",
        subject_type="document",
        subject_id=document_id,
        details={"volunteer_id": volunteer_id},
    )
    return RedirectResponse(url=f"/volunteers/{volunteer_id}", status_code=status.HTTP_303_SEE_OTHER)
