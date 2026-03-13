from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from app.api.v1.errors import ApiErrorResponse
from app.auth.dependencies import require_authenticated_user
from app.auth.roles import UserRole
from app.services.users import UsersServiceProtocol, get_users_service

router = APIRouter()


class UserListItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    user_account_id: int
    auth_user_id: str
    legacy_user_id: int | None
    username: str
    email: str
    display_name: str | None
    role: str
    last_login: datetime | None
    group_admin_group_ids: list[int]
    group_admin_group_count: int


class UserDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    user_account_id: int
    auth_user_id: str
    legacy_user_id: int | None
    username: str
    email: str
    display_name: str | None
    role: str
    last_login: datetime | None
    created_at: datetime
    migrated_at: datetime | None
    group_admin_group_ids: list[int]


def _get_users_service_for_request(request: Request) -> UsersServiceProtocol:
    if getattr(request.app.state, "users_service", None) is not None:
        return request.app.state.users_service
    return get_users_service()


def require_admin_user(current_user=Depends(require_authenticated_user)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Admin access is required."},
        )
    return current_user


def _to_user_list_response(user) -> UserListItemResponse:
    return UserListItemResponse(
        user_account_id=user.user_account_id,
        auth_user_id=str(user.auth_user_id),
        legacy_user_id=user.legacy_user_id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role.name.lower(),
        last_login=user.last_login,
        group_admin_group_ids=user.group_admin_group_ids,
        group_admin_group_count=user.group_admin_group_count,
    )


def _to_user_detail_response(user) -> UserDetailResponse:
    return UserDetailResponse(
        user_account_id=user.user_account_id,
        auth_user_id=str(user.auth_user_id),
        legacy_user_id=user.legacy_user_id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role.name.lower(),
        last_login=user.last_login,
        created_at=user.created_at,
        migrated_at=user.migrated_at,
        group_admin_group_ids=user.group_admin_group_ids,
    )


@router.get(
    "/users",
    response_model=list[UserListItemResponse],
    responses={403: {"model": ApiErrorResponse}, 503: {"model": ApiErrorResponse}},
)
async def list_users(
    request: Request,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
    _current_user=Depends(require_admin_user),
):
    try:
        users = await _get_users_service_for_request(request).list_users(query=q, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "users_unavailable", "message": str(exc)},
        ) from exc
    return [_to_user_list_response(user) for user in users]


@router.get(
    "/users/{user_account_id}",
    response_model=UserDetailResponse,
    responses={403: {"model": ApiErrorResponse}, 404: {"model": ApiErrorResponse}, 503: {"model": ApiErrorResponse}},
)
async def get_user_detail(
    request: Request,
    user_account_id: int,
    _current_user=Depends(require_admin_user),
):
    try:
        user = await _get_users_service_for_request(request).get_user_detail(user_account_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "users_unavailable", "message": str(exc)},
        ) from exc
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "user_not_found", "message": f"User account {user_account_id} was not found."},
        )
    return _to_user_detail_response(user)
