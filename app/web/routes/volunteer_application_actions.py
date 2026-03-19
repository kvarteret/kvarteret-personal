from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.dependencies import (
    get_volunteer_applications_service,
    get_volunteers_service,
    require_management_user,
)
from app.errors import NotConfiguredError
from app.observability import log_admin_activity
from app.services.volunteer_applications import (
    VolunteerApplicationConflictError,
    VolunteerAlreadyExistsError,
    VolunteerApplicationNotFoundError,
    VolunteerApplicationSubmissionInput,
    VolunteerApplicationsService,
)
from app.services.volunteers import VolunteersService
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
    invite = await volunteer_applications_service.create_volunteer_application_invitation(
        email,
        initial_group_id=parsed_group_id,
        initial_role_id=parsed_role_id,
    )
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
    return RedirectResponse(url="/volunteer-applications", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/volunteer-applications/{application_id}/approval")
async def volunteer_application_approve(
    request: Request,
    application_id: int,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    try:
        volunteer_id = await volunteer_applications_service.approve_volunteer_application(application_id)
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
    return RedirectResponse(url=f"/volunteers/{volunteer_id}", status_code=status.HTTP_303_SEE_OTHER)


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
    if request.headers.get("HX-Request") == "true":
        volunteer_applications = await volunteer_applications_service.list_volunteer_applications()
        return templates.TemplateResponse(
            request,
            "components/volunteer_applications_list.html",
            {
                "current_user": current_user,
                "volunteer_applications": volunteer_applications,
            },
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
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    try:
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
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except VolunteerApplicationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except NotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return RedirectResponse(url=f"/apply/{token}/submitted", status_code=status.HTTP_303_SEE_OTHER)

