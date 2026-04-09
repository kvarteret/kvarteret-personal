from __future__ import annotations

from datetime import date

from posthog import capture, identify_context, new_context

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse

from app.dependencies import (
    get_settings,
    get_volunteer_applications_service,
    get_volunteers_service,
    require_management_user,
)
from app.errors import NotConfiguredError
from app.observability import log_admin_activity
from app.infrastructure.media.photo_processing import InvalidPhotoError, PhotoUploadTooLargeError
from app.domain.volunteer_applications.service import (
    VolunteerApplicationConflictError,
    VolunteerAlreadyExistsError,
    VolunteerApplicationNotFoundError,
    VolunteerApplicationSubmissionInput,
    VolunteerApplicationValidationError,
    VolunteerApplicationsService,
)
from app.domain.volunteers.service import VolunteersService
from app.web.upload_helpers import read_upload_file_limited
from app.web.templates import templates

router = APIRouter()


@router.post("/volunteer-applications")
async def volunteer_applications_create_invite(
    request: Request,
    email: str = Form(...),
    group_id: str | None = Form(default=None),
    role_id: str | None = Form(default=None),
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    parsed_group_id = int(group_id) if group_id and group_id.strip() else None
    parsed_role_id = int(role_id) if role_id and role_id.strip() else None
    if (parsed_group_id is None) != (parsed_role_id is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose both group and verv, or leave both empty.",
        )
    if parsed_group_id is not None and parsed_role_id is not None:
        available_roles = await volunteers_service.list_assignment_roles(parsed_group_id)
        if not any(role.role_id == parsed_role_id for role in available_roles):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected verv does not belong to the chosen group.",
            )
    try:
        invite = await volunteer_applications_service.create_volunteer_application_invitation(
            email,
            base_url=str(request.base_url).rstrip("/"),
            initial_group_id=parsed_group_id,
            initial_role_id=parsed_role_id,
        )
    except VolunteerAlreadyExistsError as exc:
        return RedirectResponse(url=f"/volunteers/{exc.volunteer_id}", status_code=status.HTTP_303_SEE_OTHER)
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.create_invite",
        subject_type="volunteer_application",
        details={
            "email": email.strip().lower(),
            "initial_group_id": invite.initial_group_id,
            "initial_role_id": invite.initial_role_id,
        },
    )
    with new_context():
        identify_context(str(current_user.auth_user_id))
        capture("volunteer_application_invite_created", properties={
            "has_initial_group": invite.initial_group_id is not None,
        })
    return RedirectResponse(url="/volunteer-applications", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/volunteer-applications/{application_id}/approval")
async def volunteer_application_approve(
    request: Request,
    application_id: int,
    accepted_group_id: str | None = Form(default=None),
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    parsed_group_id = int(accepted_group_id) if accepted_group_id and accepted_group_id.strip() else None
    try:
        volunteer_id = await volunteer_applications_service.approve_volunteer_application(
            application_id,
            accepted_group_id=parsed_group_id,
            base_url=str(request.base_url).rstrip("/"),
        )
    except VolunteerAlreadyExistsError as exc:
        return RedirectResponse(
            url=f"/volunteers/{exc.volunteer_id}?duplicate_application_id={application_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
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
    with new_context():
        identify_context(str(current_user.auth_user_id))
        capture("volunteer_application_approved", properties={"has_accepted_group": parsed_group_id is not None})
    return RedirectResponse(url=f"/volunteers/{volunteer_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/volunteer-applications/{application_id}/trial-attendance")
async def volunteer_application_mark_trial_attendance(
    request: Request,
    application_id: int,
    attended: str = Form(...),
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    try:
        detail = await volunteer_applications_service.mark_trial_shift_attended(
            application_id,
            attended=attended == "true",
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.mark_trial_attendance",
        subject_type="volunteer_application",
        subject_id=application_id,
        details={"attended": detail.trial_shift_attended},
    )
    return RedirectResponse(
        url=f"/volunteer-applications/{application_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.delete("/volunteer-applications/{application_id}")
async def volunteer_application_delete(
    request: Request,
    application_id: int,
    current_user=Depends(require_management_user),
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
    with new_context():
        identify_context(str(current_user.auth_user_id))
        capture("volunteer_application_deleted")
    if request.headers.get("HX-Request") == "true" and request.headers.get("HX-Boosted") != "true":
        volunteer_applications = await volunteer_applications_service.list_volunteer_applications()
        return templates.TemplateResponse(
            request,
            "components/volunteer_applications/volunteer_applications_list.html",
            {
                "current_user": current_user,
                "volunteer_applications": volunteer_applications,
            },
    )
    return RedirectResponse(url="/volunteer-applications", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/volunteer-applications/{application_id}/resend")
async def volunteer_application_resend(
    request: Request,
    application_id: int,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    try:
        detail = await volunteer_applications_service.resend_volunteer_application_invitation(
            application_id,
            base_url=str(request.base_url).rstrip("/"),
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.resend_invite",
        subject_type="volunteer_application",
        subject_id=application_id,
        details={"email": detail.email},
    )
    return RedirectResponse(url="/volunteer-applications", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/apply/{token}")
async def volunteer_application_submit(
    request: Request,
    token: str,
    first_name: str | None = Form(default=None),
    last_name: str = Form(...),
    phone: str = Form(...),
    birth_date: str | None = Form(default=None),
    gender: str = Form(default="A"),
    address: str | None = Form(default=None),
    postal_code: str | None = Form(default=None),
    profile_photo: UploadFile | None = File(default=None),
    settings=Depends(get_settings),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    try:
        photo_content = (
            await read_upload_file_limited(profile_photo, max_bytes=settings.photo_upload_max_bytes)
            if profile_photo is not None and profile_photo.filename
            else None
        )
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
            ),
            base_url=str(request.base_url).rstrip("/"),
            photo_filename=profile_photo.filename if profile_photo is not None else None,
            photo_content=photo_content,
            photo_content_type=profile_photo.content_type if profile_photo is not None else None,
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except VolunteerApplicationValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except VolunteerApplicationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PhotoUploadTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    except InvalidPhotoError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except NotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    finally:
        if profile_photo is not None:
            await profile_photo.close()
    with new_context():
        capture("volunteer_application_submitted", properties={"has_photo": profile_photo is not None and bool(profile_photo.filename)})
    return RedirectResponse(url=f"/apply/{token}/submitted", status_code=status.HTTP_303_SEE_OTHER)
