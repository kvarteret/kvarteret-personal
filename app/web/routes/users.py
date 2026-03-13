from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_users_service, require_web_admin_user
from app.errors import NotConfiguredError
from app.observability import log_admin_activity
from app.services.users import UsersService
from app.web.templates import templates

router = APIRouter()


@router.get("/users")
async def users_index(
    request: Request,
    q: str | None = None,
    current_user=Depends(require_web_admin_user),
    users_service: UsersService = Depends(get_users_service),
):
    try:
        users = await users_service.list_users(query=q, limit=100)
    except NotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed user views are not configured yet.",
        )
    log_admin_activity(
        request=request,
        user=current_user,
        action="user.list",
        subject_type="user_account",
        details={"query": q or "", "result_count": len(users)},
    )
    return templates.TemplateResponse(
        request,
        "pages/users.html",
        {
            "title": "Users",
            "section": "users",
            "current_user": current_user,
            "users": users,
            "query": q or "",
        },
    )


@router.get("/users/{user_account_id}")
async def users_detail(
    request: Request,
    user_account_id: int,
    current_user=Depends(require_web_admin_user),
    users_service: UsersService = Depends(get_users_service),
):
    try:
        user = await users_service.get_user_detail(user_account_id)
    except NotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database-backed user views are not configured yet.",
        )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    log_admin_activity(
        request=request,
        user=current_user,
        action="user.view_detail",
        subject_type="user_account",
        subject_id=user_account_id,
    )
    return templates.TemplateResponse(
        request,
        "pages/user_detail.html",
        {
            "title": user.username,
            "section": "users",
            "current_user": current_user,
            "user_account": user,
        },
    )
