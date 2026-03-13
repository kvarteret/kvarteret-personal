from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.api.v1.errors import ApiErrorResponse
from app.auth.dependencies import require_authenticated_user
from app.auth.roles import UserRole
from app.services.people import (
    DocumentNotFoundError,
    DocumentUploadResult,
    DuplicateDocumentError,
    PeopleServiceProtocol,
    PersonNotFoundError,
    PhotoUploadResult,
    UnsupportedUploadError,
    get_people_service,
)

router = APIRouter()


class PersonListItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    person_id: int
    first_name: str | None
    last_name: str
    full_name: str
    email: str | None
    phone: str | None
    birth_date: date | None
    created_at: datetime
    photo_url: str | None


class NextOfKinResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    next_of_kin_id: int
    name: str
    phone: str


class CardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    card_id: int
    card_number: str


class DocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    document_id: int
    filename: str
    filetype: str | None
    group_id: int | None
    created_at: datetime | None = None
    storage_path: str
    download_url: str | None


class MembershipResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    history_id: int
    group_id: int
    group_name: str
    role_id: int | None
    role_name: str | None
    semester_code: int
    semester_label: str
    contract_signed: bool


class PersonDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    person_id: int
    first_name: str | None
    last_name: str
    full_name: str
    email: str | None
    phone: str | None
    birth_date: date | None
    created_at: datetime
    gender: str
    address: str | None
    postal_code: str | None
    employment_status: int | None
    photo_url: str | None
    documents: list[DocumentResponse]
    next_of_kin: list[NextOfKinResponse]
    cards: list[CardResponse]
    recent_memberships: list[MembershipResponse]


class PhotoUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    person_id: int
    photo_url: str
    storage_path: str


def _get_people_service_for_request(request: Request) -> PeopleServiceProtocol:
    if getattr(request.app.state, "people_service", None) is not None:
        return request.app.state.people_service
    return get_people_service()


def _require_admin(current_user):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Admin access is required."},
        )
    return current_user


@router.get(
    "/people",
    response_model=list[PersonListItemResponse],
    responses={503: {"model": ApiErrorResponse}},
)
async def list_people(
    request: Request,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    _current_user=Depends(require_authenticated_user),
):
    people = await _get_people_service_for_request(request).list_people(query=q, limit=limit)
    return [PersonListItemResponse.model_validate(person) for person in people]


@router.get(
    "/people/{person_id}",
    response_model=PersonDetailResponse,
    responses={404: {"model": ApiErrorResponse}, 503: {"model": ApiErrorResponse}},
)
async def get_person_detail(
    request: Request,
    person_id: int,
    _current_user=Depends(require_authenticated_user),
):
    person = await _get_people_service_for_request(request).get_person_detail(person_id)
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "person_not_found", "message": f"Person {person_id} was not found."},
        )
    return PersonDetailResponse.model_validate(person)


@router.post(
    "/people/{person_id}/photo",
    response_model=PhotoUploadResponse,
    responses={400: {"model": ApiErrorResponse}, 403: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
)
async def upload_person_photo(
    request: Request,
    person_id: int,
    file: UploadFile = File(...),
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    service = _get_people_service_for_request(request)
    try:
        result = await service.upload_photo(
            person_id=person_id,
            filename=file.filename or "photo",
            content=await file.read(),
            content_type=file.content_type,
        )
    except PersonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "person_not_found", "message": str(exc)}) from exc
    except UnsupportedUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_upload", "message": str(exc)}) from exc
    return PhotoUploadResponse.model_validate(result)


@router.delete(
    "/people/{person_id}/photo",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={403: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
)
async def delete_person_photo(
    request: Request,
    person_id: int,
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    service = _get_people_service_for_request(request)
    try:
        await service.delete_photo(person_id)
    except PersonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "photo_not_found", "message": str(exc)}) from exc


@router.post(
    "/people/{person_id}/documents",
    response_model=DocumentResponse,
    responses={400: {"model": ApiErrorResponse}, 403: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}, 409: {"model": ApiErrorResponse}},
)
async def upload_person_document(
    request: Request,
    person_id: int,
    file: UploadFile = File(...),
    group_id: str | None = Form(default=None),
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    service = _get_people_service_for_request(request)
    try:
        result: DocumentUploadResult = await service.upload_document(
            person_id=person_id,
            filename=file.filename or "document",
            content=await file.read(),
            content_type=file.content_type,
            group_id=int(group_id) if group_id and group_id.strip() else None,
        )
    except PersonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "person_not_found", "message": str(exc)}) from exc
    except DuplicateDocumentError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "duplicate_document", "message": str(exc)}) from exc
    except UnsupportedUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_upload", "message": str(exc)}) from exc
    return DocumentResponse.model_validate(result)


@router.delete(
    "/people/{person_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={403: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
)
async def delete_person_document(
    request: Request,
    person_id: int,
    document_id: int,
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    service = _get_people_service_for_request(request)
    try:
        await service.delete_document(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "document_not_found", "message": str(exc)}) from exc
