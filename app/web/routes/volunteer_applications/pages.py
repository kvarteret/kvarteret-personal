from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import (
    get_email_outbox_service,
    get_current_user,
    get_volunteer_applications_service,
    get_volunteers_service,
    require_management_user,
)
from app.email_outbox_service import EmailOutboxService
from app.observability import log_admin_activity
from app.domain.volunteer_applications.service import VolunteerApplicationsService
from app.domain.volunteers.options import SEMESTER_TERM_OPTIONS, gender_label
from app.domain.volunteers.service import VolunteersService
from app.shared.semester import get_current_semester_code
from app.web.i18n import (
    activate_public_locale,
    apply_locale_vary_header,
    resolve_public_locale,
    translate_public,
)
from app.web.templates import templates

_APP_NOT_FOUND = "Volunteer application not found."

router = APIRouter()


@router.get("/volunteer-applications")
async def volunteer_applications_index(
    request: Request,
    q: str | None = None,
    application_status: str | None = "active",
    group_id: int | None = None,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(
        get_volunteer_applications_service
    ),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    volunteer_applications = (
        await volunteer_applications_service.list_volunteer_applications(
            query=q,
            application_status=application_status,
            group_id=group_id,
        )
    )
    recent_registrations_page = (
        await volunteer_applications_service.list_recent_volunteer_registrations_page(
            limit=10
        )
    )
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
            "application_query": q or "",
            "selected_application_status": application_status if application_status is not None else "active",
            "selected_application_group_id": group_id,
        },
    )


@router.get("/volunteer-applications/assignment-fields")
async def volunteer_application_assignment_fields(
    request: Request,
    group_id: int | None = None,
    accepted_group_id: int | None = None,
    application_id: int | None = None,
    current_user=Depends(require_management_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
    volunteer_applications_service: VolunteerApplicationsService = Depends(
        get_volunteer_applications_service
    ),
):
    if application_id is not None:
        application = (
            await volunteer_applications_service.get_volunteer_application_detail(
                application_id
            )
        )
        if application is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_APP_NOT_FOUND
            )
        group_options = _build_promotion_group_options(application)
    else:
        group_options = await volunteers_service.list_assignment_groups()
    selected_group_id = group_id if group_id is not None else accepted_group_id
    role_options = (
        await volunteers_service.list_assignment_roles(selected_group_id)
        if selected_group_id is not None
        else []
    )
    return templates.TemplateResponse(
        request,
        "components/volunteer_applications/volunteer_application_assignment_fields.html",
        {
            "current_user": current_user,
            "group_options": group_options,
            "selected_group_id": selected_group_id,
            "role_options": role_options,
            "application_id": application_id,
            "group_field_name": "accepted_group_id" if application_id else "group_id",
            "role_field_name": "accepted_role_id" if application_id else "role_id",
            "role_required": application_id is not None,
        },
    )


@router.get("/volunteer-applications/recent-registrations")
async def volunteer_recent_registrations(
    request: Request,
    cursor: str | None = None,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(
        get_volunteer_applications_service
    ),
):
    recent_registrations_page = (
        await volunteer_applications_service.list_recent_volunteer_registrations_page(
            limit=10,
            cursor=cursor,
        )
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
    volunteer_applications_service: VolunteerApplicationsService = Depends(
        get_volunteer_applications_service
    ),
):
    locale = resolve_public_locale(request.headers.get("Accept-Language"))
    volunteer_application = (
        await volunteer_applications_service.get_volunteer_application_by_token(token)
    )
    if volunteer_application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate_public(locale, _APP_NOT_FOUND),
        )
    return _render_public_apply_template(
        request,
        "pages/volunteer_applications/volunteer_application_form.html",
        locale=locale,
        current_user=current_user,
        title=translate_public(locale, "Volunteer registration"),
        volunteer_application=volunteer_application,
        gender_options=_localized_gender_options(locale),
        submitted=False,
        form_error=None,
        form_values={},
    )


@router.get("/apply/{token}/submitted")
async def volunteer_application_submitted(
    request: Request,
    token: str,
    current_user=Depends(get_current_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(
        get_volunteer_applications_service
    ),
):
    locale = resolve_public_locale(request.headers.get("Accept-Language"))
    volunteer_application = (
        await volunteer_applications_service.get_volunteer_application_by_token(token)
    )
    if volunteer_application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate_public(locale, _APP_NOT_FOUND),
        )
    if not volunteer_application.submitted:
        return _render_public_apply_template(
            request,
            "pages/volunteer_applications/volunteer_application_form.html",
            locale=locale,
            current_user=current_user,
            title=translate_public(locale, "Volunteer registration"),
            volunteer_application=volunteer_application,
            gender_options=_localized_gender_options(locale),
            submitted=False,
            form_error=None,
            form_values={},
        )
    return _render_public_apply_template(
        request,
        "pages/volunteer_applications/volunteer_application_submitted.html",
        locale=locale,
        current_user=current_user,
        title=translate_public(locale, "Application submitted"),
        volunteer_application=volunteer_application,
    )


@router.get("/volunteer-applications/{application_id}")
async def volunteer_application_detail(
    request: Request,
    application_id: int,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(
        get_volunteer_applications_service
    ),
    email_outbox_service: EmailOutboxService = Depends(
        get_email_outbox_service
    ),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
):
    volunteer_application = (
        await volunteer_applications_service.get_volunteer_application_detail(
            application_id
        )
    )
    if volunteer_application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_APP_NOT_FOUND
        )
    latest_email_delivery = await email_outbox_service.get_latest_for_registration(
        application_id
    )
    promotion_group_options = _build_promotion_group_options(volunteer_application)
    selected_promotion_group_id = (
        volunteer_application.initial_group_id
        or volunteer_application.first_choice_group_id
    )
    promotion_role_options = (
        await volunteers_service.list_assignment_roles(selected_promotion_group_id)
        if selected_promotion_group_id is not None
        else []
    )
    current_semester_code = get_current_semester_code()
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
            "latest_email_delivery": latest_email_delivery,
            "gender_label": gender_label,
            "promotion_group_options": promotion_group_options,
            "promotion_role_options": promotion_role_options,
            "selected_promotion_group_id": selected_promotion_group_id,
            "semester_term_options": SEMESTER_TERM_OPTIONS,
            "current_semester_code": current_semester_code,
        },
    )


def _build_promotion_group_options(volunteer_application):
    options: list[dict[str, object]] = []
    seen_group_ids: set[int] = set()
    for group_id, name in [
        (
            volunteer_application.initial_group_id,
            volunteer_application.initial_group_name,
        ),
        (
            volunteer_application.first_choice_group_id,
            volunteer_application.first_choice_group_name,
        ),
    ]:
        if group_id is None or not name or group_id in seen_group_ids:
            continue
        seen_group_ids.add(group_id)
        options.append({"group_id": group_id, "name": name})
    return options


def _render_public_apply_template(
    request: Request,
    template_name: str,
    *,
    locale: str,
    current_user,
    title: str,
    volunteer_application,
    status_code: int = 200,
    **context,
):
    with activate_public_locale(locale):
        response = templates.TemplateResponse(
            request,
            template_name,
            {
                "title": title,
                "section": "apply",
                "current_user": current_user,
                "page_lang": locale,
                "volunteer_application": volunteer_application,
                **context,
            },
            status_code=status_code,
        )
    apply_locale_vary_header(response)
    return response


def _localized_gender_options(locale: str) -> tuple[dict[str, str], ...]:
    return (
        {"code": "M", "label": translate_public(locale, "Man")},
        {"code": "K", "label": translate_public(locale, "Woman")},
        {"code": "A", "label": translate_public(locale, "Other")},
    )
