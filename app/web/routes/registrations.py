from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.dependencies import get_current_user, get_registrations_service, require_web_admin_user
from app.observability import log_admin_activity
from app.services.registrations import (
    RegistrationConflictError,
    RegistrationNotFoundError,
    RegistrationSubmissionInput,
    RegistrationsService,
)
from app.web.templates import templates

router = APIRouter()


@router.get("/registrations")
async def registrations_index(
    request: Request,
    current_user=Depends(require_web_admin_user),
    registrations_service: RegistrationsService = Depends(get_registrations_service),
):
    registrations = await registrations_service.list_pending()
    log_admin_activity(
        request=request,
        user=current_user,
        action="registration.list",
        subject_type="registration",
        details={"result_count": len(registrations)},
    )
    return templates.TemplateResponse(
        request,
        "pages/registrations.html",
        {
            "title": "Registrations",
            "section": "registrations",
            "current_user": current_user,
            "registrations": registrations,
        },
    )


@router.post("/registrations")
async def registrations_create_invite(
    request: Request,
    email: str = Form(...),
    current_user=Depends(require_web_admin_user),
    registrations_service: RegistrationsService = Depends(get_registrations_service),
):
    await registrations_service.create_invitation(email)
    log_admin_activity(
        request=request,
        user=current_user,
        action="registration.create_invite",
        subject_type="registration",
        details={"email": email.strip().lower()},
    )
    return RedirectResponse(url="/registrations", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/registrations/{registration_id}/approve")
async def registrations_approve(
    request: Request,
    registration_id: int,
    current_user=Depends(require_web_admin_user),
    registrations_service: RegistrationsService = Depends(get_registrations_service),
):
    try:
        person_id = await registrations_service.approve_registration(registration_id)
    except (RegistrationNotFoundError, RegistrationConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="registration.approve",
        subject_type="registration",
        subject_id=registration_id,
        details={"person_id": person_id},
    )
    return RedirectResponse(url=f"/people/{person_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/registrations/{registration_id}/reject")
async def registrations_reject(
    request: Request,
    registration_id: int,
    current_user=Depends(require_web_admin_user),
    registrations_service: RegistrationsService = Depends(get_registrations_service),
):
    try:
        await registrations_service.reject_registration(registration_id)
    except RegistrationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    log_admin_activity(
        request=request,
        user=current_user,
        action="registration.reject",
        subject_type="registration",
        subject_id=registration_id,
    )
    return RedirectResponse(url="/registrations", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/register/{token}")
async def registration_form(
    request: Request,
    token: str,
    current_user=Depends(get_current_user),
    registrations_service: RegistrationsService = Depends(get_registrations_service),
):
    detail = await registrations_service.get_invitation_by_token(token)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registration not found.")
    return templates.TemplateResponse(
        request,
        "pages/register_form.html",
        {
            "title": "Volunteer registration",
            "section": "register",
            "current_user": current_user,
            "registration": detail,
        },
    )


@router.post("/register/{token}")
async def registration_submit(
    request: Request,
    token: str,
    first_name: str | None = Form(default=None),
    last_name: str = Form(...),
    phone: str | None = Form(default=None),
    birth_date: str | None = Form(default=None),
    gender: str = Form(default="A"),
    address: str | None = Form(default=None),
    postal_code: str | None = Form(default=None),
    employment_status: str | None = Form(default=None),
    current_user=Depends(get_current_user),
    registrations_service: RegistrationsService = Depends(get_registrations_service),
):
    try:
        detail = await registrations_service.submit_registration(
            token,
            RegistrationSubmissionInput(
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
    except RegistrationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RegistrationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "pages/register_form.html",
        {
            "title": "Volunteer registration",
            "section": "register",
            "current_user": current_user,
            "registration": detail,
            "submitted": True,
        },
    )
