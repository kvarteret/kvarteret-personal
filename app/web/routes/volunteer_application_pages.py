from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_current_user, get_volunteer_applications_service, require_web_admin_user
from app.observability import log_admin_activity
from app.services.volunteer_applications import VolunteerApplicationsService
from app.services.volunteer_options import GENDER_OPTIONS
from app.web.templates import templates

router = APIRouter()


@router.get("/volunteer-applications")
async def volunteer_applications_index(
    request: Request,
    current_user=Depends(require_web_admin_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    volunteer_applications = await volunteer_applications_service.list_volunteer_applications()
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
