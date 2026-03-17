from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse

from app.dependencies import get_volunteer_applications_service, require_web_admin_user
from app.errors import NotConfiguredError
from app.observability import log_admin_activity
from app.services.volunteer_applications import (
    VolunteerApplicationConflictError,
    VolunteerApplicationNotFoundError,
    VolunteerApplicationSubmissionInput,
    VolunteerApplicationsService,
)

router = APIRouter()


@router.post("/volunteer-applications")
async def volunteer_applications_create_invite(
    request: Request,
    email: str = Form(...),
    current_user=Depends(require_web_admin_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    await volunteer_applications_service.create_volunteer_application_invitation(email)
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.create_invite",
        subject_type="volunteer_application",
        details={"email": email.strip().lower()},
    )
    return RedirectResponse(url="/volunteer-applications", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/volunteer-applications/{application_id}/approval")
async def volunteer_application_approve(
    request: Request,
    application_id: int,
    current_user=Depends(require_web_admin_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    try:
        volunteer_id = await volunteer_applications_service.approve_volunteer_application(application_id)
    except (VolunteerApplicationNotFoundError, VolunteerApplicationConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.approve",
        subject_type="volunteer_application",
        subject_id=application_id,
        details={"volunteer_id": volunteer_id},
    )
    return RedirectResponse(url=f"/volunteers/{volunteer_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.delete("/volunteer-applications/{application_id}")
async def volunteer_application_delete(
    request: Request,
    application_id: int,
    current_user=Depends(require_web_admin_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    try:
        await volunteer_applications_service.delete_volunteer_application(application_id)
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.delete",
        subject_type="volunteer_application",
        subject_id=application_id,
    )
    return RedirectResponse(url="/volunteer-applications", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/apply/{token}")
async def volunteer_application_submit(
    token: str,
    first_name: str | None = Form(default=None),
    last_name: str = Form(...),
    phone: str | None = Form(default=None),
    birth_date: str | None = Form(default=None),
    gender: str = Form(default="A"),
    address: str | None = Form(default=None),
    postal_code: str | None = Form(default=None),
    employment_status: str | None = Form(default=None),
    profile_photo: UploadFile | None = File(default=None),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    try:
        photo_content = await profile_photo.read() if profile_photo and profile_photo.filename else None
        await volunteer_applications_service.submit_volunteer_application(
            token,
            VolunteerApplicationSubmissionInput(
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                birth_date=date.fromisoformat(birth_date) if birth_date else None,
                gender=gender,
                address=address,
                postal_code=postal_code,
                employment_status=int(employment_status) if employment_status and employment_status.strip() else None,
            ),
            photo_filename=profile_photo.filename if profile_photo and profile_photo.filename else None,
            photo_content=photo_content,
            photo_content_type=profile_photo.content_type if profile_photo else None,
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except VolunteerApplicationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except NotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return RedirectResponse(url=f"/apply/{token}", status_code=status.HTTP_303_SEE_OTHER)
