from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_current_user, get_volunteer_applications_service, get_volunteers_service, require_admin_user
from app.observability import log_admin_activity
from app.services.volunteer_applications import VolunteerApplicationsService
from app.services.volunteer_options import GENDER_OPTIONS
from app.services.volunteers import VolunteersService
from app.web.templates import templates

router = APIRouter()


@router.get("/volunteer-applications")
async def volunteer_applications_index(
    request: Request,
    current_user=Depends(require_admin_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    volunteer_applications = await volunteer_applications_service.list_volunteer_applications()
    group_options = await volunteers_service.list_assignment_groups()
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.list",
        subject_type="volunteer_application",
        details={"result_count": len(volunteer_applications)},
    )
    return templates.TemplateResponse(
        request,
        "pages/volunteer_applications_index.html",
        {
            "title": "Volunteer Applications",
            "section": "volunteer-applications",
            "current_user": current_user,
            "volunteer_applications": volunteer_applications,
            "group_options": group_options,
            "role_options": [],
            "selected_group_id": None,
        },
    )


@router.get("/volunteer-applications/assignment-fields")
async def volunteer_application_assignment_fields(
    request: Request,
    group_id: int | None = None,
    current_user=Depends(require_admin_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    group_options = await volunteers_service.list_assignment_groups()
    selected_group_id = group_id if group_id is not None else None
    role_options = await volunteers_service.list_assignment_roles(selected_group_id) if selected_group_id is not None else []
    return templates.TemplateResponse(
        request,
        "components/volunteer_application_assignment_fields.html",
        {
            "current_user": current_user,
            "group_options": group_options,
            "selected_group_id": selected_group_id,
            "role_options": role_options,
        },
    )


@router.get("/apply/{token}")
async def volunteer_application_form(
    request: Request,
    token: str,
    current_user=Depends(get_current_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    volunteer_application = await volunteer_applications_service.get_volunteer_application_by_token(token)
    if volunteer_application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Volunteer application not found.")
    return templates.TemplateResponse(
        request,
        "pages/volunteer_application_form.html",
        {
            "title": "Volunteer registration",
            "section": "apply",
            "current_user": current_user,
            "volunteer_application": volunteer_application,
            "gender_options": GENDER_OPTIONS,
        },
    )


@router.get("/apply/{token}/submitted")
async def volunteer_application_submitted(
    request: Request,
    token: str,
    current_user=Depends(get_current_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    volunteer_application = await volunteer_applications_service.get_volunteer_application_by_token(token)
    if volunteer_application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Volunteer application not found.")
    if not volunteer_application.submitted:
        return templates.TemplateResponse(
            request,
            "pages/volunteer_application_form.html",
            {
                "title": "Volunteer registration",
                "section": "apply",
                "current_user": current_user,
                "volunteer_application": volunteer_application,
                "gender_options": GENDER_OPTIONS,
            },
        )
    return templates.TemplateResponse(
        request,
        "pages/volunteer_application_submitted.html",
        {
            "title": "Application submitted",
            "section": "apply",
            "current_user": current_user,
            "volunteer_application": volunteer_application,
        },
    )
