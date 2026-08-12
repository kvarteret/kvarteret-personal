from __future__ import annotations

from datetime import date

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
    VolunteerApplicationAdminUpdateInput,
    VolunteerAlreadyExistsError,
    VolunteerApplicationNotFoundError,
    VolunteerApplicationSubmissionInput,
    VolunteerApplicationValidationError,
    VolunteerApplicationsService,
)
from app.domain.volunteers.service import VolunteersService
from app.web.i18n import resolve_public_locale, translate_public
from app.web.routes.volunteer_applications.pages import (
    _localized_gender_options,
    _render_public_apply_template,
)
from app.web.upload_helpers import read_upload_file_limited
from app.web.templates import templates

_VOLUNTEER_APPS_PATH = "/volunteer-applications"

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
            actor_user_account_id=current_user.user_account_id,
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
    return RedirectResponse(url=_VOLUNTEER_APPS_PATH, status_code=status.HTTP_303_SEE_OTHER)


@router.patch("/volunteer-applications/{application_id}")
async def volunteer_application_update_profile(
    request: Request,
    application_id: int,
    email: str = Form(...),
    first_name: str | None = Form(default=None),
    last_name: str = Form(...),
    phone: str | None = Form(default=None),
    birth_date: str | None = Form(default=None),
    gender: str = Form(default="A"),
    address: str | None = Form(default=None),
    postal_code: str | None = Form(default=None),
    study_institution: str | None = Form(default=None),
    background_details: str | None = Form(default=None),
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(
        get_volunteer_applications_service
    ),
):
    try:
        await volunteer_applications_service.update_volunteer_application_profile(
            application_id,
            VolunteerApplicationAdminUpdateInput(
                email=email,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                birth_date=date.fromisoformat(birth_date) if birth_date else None,
                gender=gender,
                address=address,
                postal_code=postal_code,
                study_institution=study_institution,
                background_details=background_details,
            ),
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (VolunteerApplicationConflictError, VolunteerApplicationValidationError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.update_profile",
        subject_type="volunteer_application",
        subject_id=application_id,
    )
    return RedirectResponse(
        url=f"/volunteer-applications/{application_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


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
            actor_user_account_id=current_user.user_account_id,
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
    return RedirectResponse(url=f"/volunteers/{volunteer_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/volunteer-applications/groups/{group_id}/approval")
async def volunteer_application_group_approve(
    request: Request,
    group_id: int,
    accepted_group_id: str = Form(...),
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    parsed_group_id = int(accepted_group_id) if accepted_group_id and accepted_group_id.strip() else None
    if parsed_group_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a group before promoting this group.")
    try:
        volunteer_ids = await volunteer_applications_service.approve_volunteer_application_group(
            group_id,
            accepted_group_id=parsed_group_id,
            base_url=str(request.base_url).rstrip("/"),
            actor_user_account_id=current_user.user_account_id,
        )
    except (VolunteerApplicationNotFoundError, VolunteerApplicationConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.approve_group",
        subject_type="volunteer_application_group",
        subject_id=group_id,
        details={"volunteer_ids": volunteer_ids},
    )
    return RedirectResponse(url=_VOLUNTEER_APPS_PATH, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/volunteer-applications/{application_id}/contact")
async def volunteer_application_mark_contacted(
    request: Request,
    application_id: int,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    try:
        detail = await volunteer_applications_service.mark_contacted(
            application_id,
            actor_user_account_id=current_user.user_account_id,
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except VolunteerApplicationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.mark_contacted",
        subject_type="volunteer_application",
        subject_id=application_id,
        details={"status": detail.status},
    )
    return RedirectResponse(
        url=f"/volunteer-applications/{application_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/volunteer-applications/{application_id}/trial")
async def volunteer_application_start_trial(
    request: Request,
    application_id: int,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(
        get_volunteer_applications_service
    ),
):
    try:
        detail = await volunteer_applications_service.start_trial(
            application_id,
            base_url=str(request.base_url).rstrip("/"),
            actor_user_account_id=current_user.user_account_id,
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except VolunteerApplicationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.start_trial",
        subject_type="volunteer_application",
        subject_id=application_id,
        details={"trial_ends_at": detail.trial_ends_at.isoformat() if detail.trial_ends_at else None},
    )
    return RedirectResponse(
        url=f"/volunteer-applications/{application_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/volunteer-applications/{application_id}/reject")
async def volunteer_application_reject(
    request: Request,
    application_id: int,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(
        get_volunteer_applications_service
    ),
):
    try:
        detail = await volunteer_applications_service.reject_volunteer_application(
            application_id,
            actor_user_account_id=current_user.user_account_id,
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except VolunteerApplicationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.reject",
        subject_type="volunteer_application",
        subject_id=application_id,
        details={"status": detail.status},
    )
    return RedirectResponse(
        url=f"/volunteer-applications/{application_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/volunteer-applications/{application_id}/reopen")
async def volunteer_application_reopen(
    request: Request,
    application_id: int,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(
        get_volunteer_applications_service
    ),
):
    try:
        detail = await volunteer_applications_service.reopen_volunteer_application(
            application_id,
            actor_user_account_id=current_user.user_account_id,
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except VolunteerApplicationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.reopen",
        subject_type="volunteer_application",
        subject_id=application_id,
        details={"status": detail.status},
    )
    return RedirectResponse(
        url=f"/volunteer-applications/{application_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/volunteer-applications/{application_id}/restore-volunteer")
async def volunteer_application_restore_volunteer(
    request: Request,
    application_id: int,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(
        get_volunteer_applications_service
    ),
):
    try:
        detail = await volunteer_applications_service.restore_volunteer_application(
            application_id,
            actor_user_account_id=current_user.user_account_id,
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except VolunteerApplicationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.restore_volunteer",
        subject_type="volunteer_application",
        subject_id=application_id,
        details={"status": detail.status},
    )
    return RedirectResponse(
        url=f"/volunteer-applications/{application_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/volunteer-applications/{application_id}/drop-from-group")
async def volunteer_application_drop_from_group(
    request: Request,
    application_id: int,
    current_user=Depends(require_management_user),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    try:
        await volunteer_applications_service.drop_group_invitee(
            application_id,
            dropped_by_user_id=current_user.user_account_id,
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except VolunteerApplicationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.drop_group_invitee",
        subject_type="volunteer_application",
        subject_id=application_id,
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
        await volunteer_applications_service.delete_volunteer_application(
            application_id,
            actor_user_account_id=current_user.user_account_id,
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except VolunteerApplicationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="volunteer_application.delete",
        subject_type="volunteer_application",
        subject_id=application_id,
    )
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
    return RedirectResponse(url=_VOLUNTEER_APPS_PATH, status_code=status.HTTP_303_SEE_OTHER)


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
            actor_user_account_id=current_user.user_account_id,
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except VolunteerApplicationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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
    return RedirectResponse(url=_VOLUNTEER_APPS_PATH, status_code=status.HTTP_303_SEE_OTHER)


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
    locale = resolve_public_locale(request.headers.get("Accept-Language"))
    has_photo = profile_photo is not None and bool(profile_photo.filename)
    parsed_birth_date = date.fromisoformat(birth_date) if birth_date else None
    submission_input = VolunteerApplicationSubmissionInput(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        birth_date=parsed_birth_date,
        gender=gender,
        address=address,
        postal_code=postal_code,
    )
    form_values = {
        "first_name": first_name or "",
        "last_name": last_name,
        "phone": phone,
        "birth_date": birth_date or "",
        "gender": gender,
        "address": address or "",
        "postal_code": postal_code or "",
    }
    try:
        photo_content = await _read_optional_upload(profile_photo, max_bytes=settings.photo_upload_max_bytes) if has_photo else None
        photo_filename = profile_photo.filename if has_photo else None
        photo_content_type = profile_photo.content_type if has_photo else None
        await volunteer_applications_service.submit_volunteer_application(
            token,
            submission_input,
            base_url=str(request.base_url).rstrip("/"),
            photo_filename=photo_filename,
            photo_content=photo_content,
            photo_content_type=photo_content_type,
        )
    except VolunteerApplicationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate_public(locale, str(exc)),
        ) from exc
    except Exception as exc:
        status_code = _apply_error_status(exc)
        if status_code is None:
            raise
        return await _render_public_apply_error_response(
            request,
            locale=locale,
            token=token,
            volunteer_applications_service=volunteer_applications_service,
            form_values=form_values,
            error_message=translate_public(locale, str(exc)),
            status_code=status_code,
        )
    finally:
        if profile_photo is not None:
            await profile_photo.close()
    return RedirectResponse(url=f"/apply/{token}/submitted", status_code=status.HTTP_303_SEE_OTHER)


async def _read_optional_upload(upload: UploadFile | None, *, max_bytes: int) -> bytes | None:
    if upload is None or not upload.filename:
        return None
    return await read_upload_file_limited(upload, max_bytes=max_bytes)


def _apply_error_status(exc: Exception) -> int | None:
    """Map known application errors to HTTP status codes. Returns None to re-raise."""
    if isinstance(exc, VolunteerApplicationValidationError):
        return status.HTTP_400_BAD_REQUEST
    if isinstance(exc, VolunteerApplicationConflictError):
        return status.HTTP_409_CONFLICT
    if isinstance(exc, PhotoUploadTooLargeError):
        return status.HTTP_413_CONTENT_TOO_LARGE
    if isinstance(exc, InvalidPhotoError):
        return status.HTTP_400_BAD_REQUEST
    if isinstance(exc, NotConfiguredError):
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return None


async def _render_public_apply_error_response(
    request: Request,
    *,
    locale: str,
    token: str,
    volunteer_applications_service: VolunteerApplicationsService,
    form_values: dict[str, str],
    error_message: str,
    status_code: int,
):
    volunteer_application = await volunteer_applications_service.get_volunteer_application_by_token(token)
    if volunteer_application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate_public(locale, "Volunteer application not found."),
        )
    return _render_public_apply_template(
        request,
        "pages/volunteer_applications/volunteer_application_form.html",
        locale=locale,
        current_user=None,
        title=translate_public(locale, "Volunteer registration"),
        volunteer_application=volunteer_application,
        gender_options=_localized_gender_options(locale),
        submitted=False,
        form_error=error_message,
        form_values=form_values,
        status_code=status_code,
    )
