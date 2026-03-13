from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr

from app.api.v1.errors import ApiErrorResponse
from app.auth.dependencies import require_authenticated_user
from app.auth.roles import UserRole
from app.services.registrations import (
    RegistrationConflictError,
    RegistrationNotFoundError,
    RegistrationSubmissionInput,
    RegistrationsServiceProtocol,
    get_registrations_service,
)

router = APIRouter()


class RegistrationInviteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class RegistrationSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = None
    last_name: str
    phone: str | None = None
    birth_date: date | None = None
    gender: str = "A"
    address: str | None = None
    postal_code: str | None = None
    employment_status: int | None = None


class RegistrationInviteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    registration_id: int
    token: str
    email: str
    created_at: datetime


class PendingRegistrationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    registration_id: int
    token: str
    email: str
    created_at: datetime
    submitted: bool
    first_name: str | None
    last_name: str | None
    phone: str | None


class PendingRegistrationDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    registration_id: int
    token: str
    email: str
    created_at: datetime
    submitted: bool
    pending_person_id: int | None
    first_name: str | None
    last_name: str | None
    phone: str | None
    birth_date: date | None
    gender: str | None
    address: str | None
    postal_code: str | None
    employment_status: int | None


class RegistrationApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_id: int


def _get_registrations_service_for_request(request: Request) -> RegistrationsServiceProtocol:
    if getattr(request.app.state, "registrations_service", None) is not None:
        return request.app.state.registrations_service
    return get_registrations_service()


def _require_admin(current_user):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Admin access is required."},
        )
    return current_user


@router.get("/registrations", response_model=list[PendingRegistrationResponse], responses={403: {"model": ApiErrorResponse}})
async def list_registrations(request: Request, current_user=Depends(require_authenticated_user)):
    _require_admin(current_user)
    service = _get_registrations_service_for_request(request)
    return [PendingRegistrationResponse.model_validate(item) for item in await service.list_pending()]


@router.post("/registrations", response_model=RegistrationInviteResponse, responses={403: {"model": ApiErrorResponse}})
async def create_registration_invite(
    request: Request,
    payload: RegistrationInviteCreateRequest,
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    service = _get_registrations_service_for_request(request)
    return RegistrationInviteResponse.model_validate(await service.create_invitation(str(payload.email)))


@router.get("/registrations/{registration_id}", response_model=PendingRegistrationDetailResponse, responses={403: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}})
async def get_registration_detail(
    request: Request,
    registration_id: int,
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    service = _get_registrations_service_for_request(request)
    detail = await service.get_pending_detail(registration_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "registration_not_found", "message": "Registration was not found."})
    return PendingRegistrationDetailResponse.model_validate(detail)


@router.post("/registrations/{registration_id}/approve", response_model=RegistrationApprovalResponse, responses={403: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}, 409: {"model": ApiErrorResponse}})
async def approve_registration(
    request: Request,
    registration_id: int,
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    service = _get_registrations_service_for_request(request)
    try:
        person_id = await service.approve_registration(registration_id)
    except RegistrationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "registration_not_found", "message": str(exc)}) from exc
    except RegistrationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "registration_conflict", "message": str(exc)}) from exc
    return RegistrationApprovalResponse(person_id=person_id)


@router.delete("/registrations/{registration_id}", status_code=status.HTTP_204_NO_CONTENT, responses={403: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}})
async def reject_registration(
    request: Request,
    registration_id: int,
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    service = _get_registrations_service_for_request(request)
    try:
        await service.reject_registration(registration_id)
    except RegistrationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "registration_not_found", "message": str(exc)}) from exc


@router.get("/registration-submissions/{token}", response_model=PendingRegistrationDetailResponse, responses={404: {"model": ApiErrorResponse}})
async def get_registration_submission(request: Request, token: str):
    service = _get_registrations_service_for_request(request)
    detail = await service.get_invitation_by_token(token)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "registration_not_found", "message": "Registration token was not found."})
    return PendingRegistrationDetailResponse.model_validate(detail)


@router.post("/registration-submissions/{token}", response_model=PendingRegistrationDetailResponse, responses={404: {"model": ApiErrorResponse}, 409: {"model": ApiErrorResponse}})
async def submit_registration(
    request: Request,
    token: str,
    payload: RegistrationSubmissionRequest,
):
    service = _get_registrations_service_for_request(request)
    try:
        detail = await service.submit_registration(token, RegistrationSubmissionInput(**payload.model_dump()))
    except RegistrationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "registration_not_found", "message": str(exc)}) from exc
    except RegistrationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "registration_conflict", "message": str(exc)}) from exc
    return PendingRegistrationDetailResponse.model_validate(detail)
