from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.roles import UserRole
from app.dependencies import get_admin_accounts_service, require_authenticated_user, require_web_admin_user
from app.errors import NotConfiguredError
from app.observability import log_admin_activity
from app.services.admin_accounts import AdminAccountsService
from app.web.route_helpers import not_configured_http_exception
from app.web.templates import templates

router = APIRouter()


@router.get("/my-account")
async def my_account_detail(
    request: Request,
    password_error: str | None = None,
    password_message: str | None = None,
    current_user=Depends(require_authenticated_user),
    admin_accounts_service: AdminAccountsService = Depends(get_admin_accounts_service),
):
    try:
        admin_account = (
            await admin_accounts_service.get_admin_account_detail(current_user.user_account_id)
            if current_user.user_account_id
            else None
        )
    except NotConfiguredError:
        raise not_configured_http_exception("Database-backed admin-account views are not configured yet.")
    if admin_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin account not found.")
    return templates.TemplateResponse(
        request,
        "pages/admin_account_profile.html",
        {
            "title": admin_account.username,
            "section": "my-account",
            "current_user": current_user,
            "admin_account": admin_account,
            "page_label": "Min konto",
            "page_heading": "Min konto",
            "save_action": "/my-account?_method=PATCH",
            "can_edit_profile": current_user.role == UserRole.ADMIN,
            "show_role_field": current_user.role == UserRole.ADMIN,
            "show_password_form": current_user.role == UserRole.ADMIN,
            "password_error_message": password_error,
            "password_success_message": password_message,
        },
    )


@router.get("/admin-accounts")
async def admin_accounts_index(
    request: Request,
    q: str | None = None,
    current_user=Depends(require_web_admin_user),
    admin_accounts_service: AdminAccountsService = Depends(get_admin_accounts_service),
):
    try:
        admin_accounts = await admin_accounts_service.list_admin_accounts(query=q, limit=100)
    except NotConfiguredError:
        raise not_configured_http_exception("Database-backed admin-account views are not configured yet.")
    log_admin_activity(
        request=request,
        user=current_user,
        action="admin_account.list",
        subject_type="admin_account",
        details={"query": q or "", "result_count": len(admin_accounts)},
    )
    return templates.TemplateResponse(
        request,
        "pages/admin_accounts_index.html",
        {
            "title": "Admin Accounts",
            "section": "admin-accounts",
            "current_user": current_user,
            "admin_accounts": admin_accounts,
            "query": q or "",
        },
    )


@router.get("/admin-accounts/new")
async def admin_account_new(
    request: Request,
    error: str | None = None,
    current_user=Depends(require_web_admin_user),
):
    return templates.TemplateResponse(
        request,
        "pages/admin_account_new.html",
        {
            "title": "Ny admin-konto",
            "section": "admin-accounts",
            "current_user": current_user,
            "error_message": error,
        },
    )


@router.get("/admin-accounts/{account_id}")
async def admin_account_detail(
    request: Request,
    account_id: int,
    current_user=Depends(require_web_admin_user),
    admin_accounts_service: AdminAccountsService = Depends(get_admin_accounts_service),
):
    try:
        admin_account = await admin_accounts_service.get_admin_account_detail(account_id)
    except NotConfiguredError:
        raise not_configured_http_exception("Database-backed admin-account views are not configured yet.")
    if admin_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin account not found.")
    log_admin_activity(
        request=request,
        user=current_user,
        action="admin_account.view_detail",
        subject_type="admin_account",
        subject_id=account_id,
    )
    return templates.TemplateResponse(
        request,
        "pages/admin_account_profile.html",
        {
            "title": admin_account.username,
            "section": "admin-accounts",
            "current_user": current_user,
            "admin_account": admin_account,
            "page_label": "Admin-konto",
            "page_heading": admin_account.display_name or admin_account.username,
            "save_action": f"/admin-accounts/{account_id}?_method=PATCH",
            "can_edit_profile": True,
            "show_role_field": True,
            "show_password_form": False,
            "password_error_message": None,
            "password_success_message": None,
        },
    )
