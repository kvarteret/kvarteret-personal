from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from app.api.v1.errors import ApiErrorResponse
from app.auth.dependencies import require_authenticated_user
from app.auth.roles import UserRole
from app.services.groups import GroupsServiceProtocol, get_groups_service
from app.services.semester_transfer import (
    SemesterTransferEntry,
    SemesterTransferGroupNotFoundError,
    SemesterTransferService,
    get_semester_transfer_service,
)

router = APIRouter()


class GroupListItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    group_id: int
    name: str
    description: str | None
    active: bool
    active_until_semester: int
    parent_group_id: int | None
    discount_step: int | None


class GroupPositionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    role_id: int
    role_name: str | None
    pingvin_points: int


class GroupMemberResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    history_id: int
    person_id: int
    person_name: str
    role_name: str | None
    semester_code: int
    semester_label: str
    contract_signed: bool


class GroupDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    group_id: int
    name: str
    description: str | None
    active: bool
    active_until_semester: int
    active_until_label: str | None
    parent_group_id: int | None
    discount_step: int | None
    created_at: datetime | None
    positions: list[GroupPositionResponse]
    recent_members: list[GroupMemberResponse]


class SemesterTransferCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    person_id: int
    person_name: str
    role_id: int | None
    role_name: str | None
    contract_signed: bool
    source_history_id: int


class SemesterTransferPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    group_id: int
    group_name: str
    source_semester: int
    source_semester_label: str | None
    target_semester: int
    target_semester_label: str | None
    candidates: list[SemesterTransferCandidateResponse]


class SemesterTransferEntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_id: int
    role_id: int | None
    contract_signed: bool = False


class ApplySemesterTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_semester: int
    entries: list[SemesterTransferEntryRequest]


class ApplySemesterTransferResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inserted_count: int


def _get_groups_service_for_request(request: Request) -> GroupsServiceProtocol:
    if getattr(request.app.state, "groups_service", None) is not None:
        return request.app.state.groups_service
    return get_groups_service()


def _get_semester_transfer_service_for_request(request: Request) -> SemesterTransferService:
    if getattr(request.app.state, "semester_transfer_service", None) is not None:
        return request.app.state.semester_transfer_service
    return get_semester_transfer_service()


def _require_admin(current_user):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Admin access is required."},
        )
    return current_user


@router.get("/groups", response_model=list[GroupListItemResponse], responses={503: {"model": ApiErrorResponse}})
async def list_groups(
    request: Request,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
    _current_user=Depends(require_authenticated_user),
):
    groups = await _get_groups_service_for_request(request).list_groups(query=q, limit=limit)
    return [GroupListItemResponse.model_validate(group) for group in groups]


@router.get("/groups/{group_id}", response_model=GroupDetailResponse, responses={404: {"model": ApiErrorResponse}})
async def get_group_detail(
    request: Request,
    group_id: int,
    _current_user=Depends(require_authenticated_user),
):
    group = await _get_groups_service_for_request(request).get_group_detail(group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "group_not_found", "message": f"Group {group_id} was not found."},
        )
    return GroupDetailResponse.model_validate(group)


@router.get(
    "/groups/{group_id}/semester-transfer",
    response_model=SemesterTransferPreviewResponse,
    responses={403: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
)
async def preview_semester_transfer(
    request: Request,
    group_id: int,
    source_semester: int | None = Query(default=None),
    target_semester: int | None = Query(default=None),
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    service = _get_semester_transfer_service_for_request(request)
    try:
        preview = await service.preview_transfer(group_id, source_semester=source_semester, target_semester=target_semester)
    except SemesterTransferGroupNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "group_not_found", "message": str(exc)}) from exc
    return SemesterTransferPreviewResponse.model_validate(preview)


@router.post(
    "/groups/{group_id}/semester-transfer",
    response_model=ApplySemesterTransferResponse,
    responses={403: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}},
)
async def apply_semester_transfer(
    request: Request,
    group_id: int,
    payload: ApplySemesterTransferRequest,
    current_user=Depends(require_authenticated_user),
):
    _require_admin(current_user)
    service = _get_semester_transfer_service_for_request(request)
    try:
        inserted_count = await service.apply_transfer(
            group_id,
            payload.target_semester,
            [SemesterTransferEntry(**entry.model_dump()) for entry in payload.entries],
        )
    except SemesterTransferGroupNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "group_not_found", "message": str(exc)}) from exc
    return ApplySemesterTransferResponse(inserted_count=inserted_count)
