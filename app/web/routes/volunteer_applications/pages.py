from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import (
    get_current_user,
    get_volunteer_applications_service,
    get_volunteers_service,
    require_management_user,
)
from app.observability import log_admin_activity
from app.domain.volunteer_applications.service import VolunteerApplicationsService
from app.domain.volunteers.options import GENDER_OPTIONS, gender_label
from app.domain.volunteers.service import VolunteersService
from app.web.templates import templates

router = APIRouter()


@router.get("/volunteer-applications")
async def volunteer_applications_index(
    request: Request,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    volunteer_applications = await volunteer_applications_service.list_volunteer_applications()
    recent_registrations_page = await volunteer_applications_service.list_recent_volunteer_registrations_page(limit=20)
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
        "pages/volunteer_applications/volunteer_applications_index.html",
        {
            "title": "Volunteer Applications",
            "section": "volunteer-applications",
            "current_user": current_user,
            "volunteer_applications": volunteer_applications,
            "recent_registrations": recent_registrations_page.items,
            "recent_registrations_cursor": recent_registrations_page.cursor,
            "recent_registrations_next_cursor": recent_registrations_page.next_cursor,
            "group_options": group_options,
            "role_options": [],
            "selected_group_id": None,
        },
    )


@router.get("/volunteer-applications/assignment-fields")
async def volunteer_application_assignment_fields(
    request: Request,
    group_id: int | None = None,
    current_user=Depends(require_management_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    group_options = await volunteers_service.list_assignment_groups()
    selected_group_id = group_id if group_id is not None else None
    role_options = await volunteers_service.list_assignment_roles(selected_group_id) if selected_group_id is not None else []
    return templates.TemplateResponse(
        request,
        "components/volunteer_applications/volunteer_application_assignment_fields.html",
        {
            "current_user": current_user,
            "group_options": group_options,
            "selected_group_id": selected_group_id,
            "role_options": role_options,
        },
    )


@router.get("/volunteer-applications/recent-registrations")
async def volunteer_recent_registrations(
    request: Request,
    cursor: str | None = None,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    recent_registrations_page = await volunteer_applications_service.list_recent_volunteer_registrations_page(
        limit=20,
        cursor=cursor,
    )
    return templates.TemplateResponse(
        request,
        "components/volunteer_applications/recent_volunteer_registrations.html",
        {
            "current_user": current_user,
            "recent_registrations": recent_registrations_page.items,
            "cursor": recent_registrations_page.cursor,
            "next_cursor": recent_registrations_page.next_cursor,
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
        "pages/volunteer_applications/volunteer_application_form.html",
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
            "pages/volunteer_applications/volunteer_application_form.html",
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
        "pages/volunteer_applications/volunteer_application_submitted.html",
        {
            "title": "Application submitted",
            "section": "apply",
            "current_user": current_user,
            "volunteer_application": volunteer_application,
        },
    )


@router.get("/volunteer-applications/{application_id}")
async def volunteer_application_detail(
    request: Request,
    application_id: int,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    volunteer_application = await volunteer_applications_service.get_volunteer_application_detail(application_id)
    if volunteer_application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Volunteer application not found.")
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.view",
        subject_type="volunteer_application",
        subject_id=application_id,
        details={"submitted": volunteer_application.submitted},
    )
    return templates.TemplateResponse(
        request,
        "pages/volunteer_applications/volunteer_application_detail.html",
        {
            "title": "Volunteer application",
            "section": "volunteer-applications",
            "current_user": current_user,
            "volunteer_application": volunteer_application,
            "gender_label": gender_label,
            "promotion_group_options": _build_promotion_group_options(volunteer_application),
        },
    )


def _build_promotion_group_options(volunteer_application):
    options: list[dict[str, object]] = []
    seen_group_ids: set[int] = set()
    for group_id, name in [
        (volunteer_application.initial_group_id, volunteer_application.initial_group_name),
        (volunteer_application.first_choice_group_id, volunteer_application.first_choice_group_name),
        (volunteer_application.second_choice_group_id, volunteer_application.second_choice_group_name),
    ]:
        if group_id is None or not name or group_id in seen_group_ids:
            continue
        seen_group_ids.add(group_id)
        options.append({"group_id": group_id, "name": name})
    return options
