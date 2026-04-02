from __future__ import annotations

from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status

from app.auth.roles import UserRole
from app.auth.cookies import SessionCookieSigner
from app.dependencies import (
    get_admin_accounts_service,
    get_mobile_card_april_state_service,
    get_session_cookie_signer,
    get_session_store,
    get_settings,
    get_supabase_auth_gateway,
    require_admin_user,
    require_authenticated_user,
)
from app.observability import log_admin_activity
from app.domain.admin_accounts.service import AdminAccountsService
from app.domain.mobile_card.april_state import MobileCardAprilStateService
from app.web.route_helpers import redirect_to

router = APIRouter()
_APRIL_TOGGLE_EMAIL = "it.leder@kvarteret.no"


def _redirect_with_error(path: str, message: str):
    separator = "&" if "?" in path else "?"
    return redirect_to(f"{path}{separator}error={quote_plus(message)}")


def _redirect_with_password_error(message: str):
    return redirect_to(f"/my-account?password_error={quote_plus(message)}")


def _set_session_cookie(response, *, request: Request, settings, session_cookie_signer: SessionCookieSigner, session_id: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_cookie_signer.sign_session_id(session_id),
        httponly=True,
        secure=request.url.scheme == "https" or settings.app_env == "production",
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
    )


@router.patch("/my-account")
async def my_account_update(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    display_name: str | None = Form(default=None),
    role: str = Form(...),
    current_user=Depends(require_authenticated_user),
    admin_accounts_service: AdminAccountsService = Depends(get_admin_accounts_service),
    session_store=Depends(get_session_store),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access is required.")
    if current_user.user_account_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin account not found.")
    try:
        role_value = UserRole(role)
        admin_account = await admin_accounts_service.update_admin_account(
            user_account_id=current_user.user_account_id,
            username=username,
            email=email,
            display_name=display_name,
            role=role_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role.") from exc
    if admin_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin account not found.")
    session = getattr(request.state, "session", None)
    if session is not None:
        session_store.invalidate_session_cache(session.session_id)
    return redirect_to("/my-account")


@router.post("/my-account/password")
async def my_account_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    current_user=Depends(require_authenticated_user),
    supabase_auth_gateway=Depends(get_supabase_auth_gateway),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access is required.")
    if len(new_password) < 8:
        return _redirect_with_password_error("Det nye passordet må være minst 8 tegn.")
    if new_password != confirm_password:
        return _redirect_with_password_error("Passordene må være like.")
    verified_auth_user_id = await supabase_auth_gateway.sign_in_with_password(current_user.email, current_password)
    if verified_auth_user_id != current_user.auth_user_id:
        return _redirect_with_password_error("Nåværende passord er feil.")
    await supabase_auth_gateway.update_user_password(current_user.auth_user_id, new_password)
    log_admin_activity(
        request=request,
        user=current_user,
        action="admin_account.change_password",
        subject_type="admin_account",
        subject_id=current_user.user_account_id,
    )
    return redirect_to("/my-account?password_message=Passordet+ble+oppdatert.")


@router.post("/admin-accounts")
async def admin_account_create(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    display_name: str | None = Form(default=None),
    role: str = Form(...),
    current_user=Depends(require_admin_user),
    admin_accounts_service: AdminAccountsService = Depends(get_admin_accounts_service),
    supabase_auth_gateway=Depends(get_supabase_auth_gateway),
):
    try:
        role_value = UserRole(role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role.") from exc

    auth_user_id = None
    try:
        auth_user_id = await supabase_auth_gateway.invite_user(
            email=email.strip(),
            metadata={
                "username": username.strip(),
                "display_name": display_name.strip() if display_name and display_name.strip() else None,
                "role": role_value.value,
            },
        )
        admin_account = await admin_accounts_service.create_admin_account(
            auth_user_id=auth_user_id,
            username=username,
            email=email,
            display_name=display_name,
            role=role_value,
        )
    except ValueError as exc:
        if auth_user_id is not None:
            await supabase_auth_gateway.delete_user(auth_user_id)
        return _redirect_with_error("/admin-accounts/new", str(exc))
    except Exception as exc:
        if auth_user_id is not None:
            await supabase_auth_gateway.delete_user(auth_user_id)
        return _redirect_with_error("/admin-accounts/new", str(exc))

    log_admin_activity(
        request=request,
        user=current_user,
        action="admin_account.create",
        subject_type="admin_account",
        subject_id=admin_account.user_account_id,
        details={"role": admin_account.role.value, "delivery": "invite_email"},
    )
    return redirect_to(f"/admin-accounts/{admin_account.user_account_id}")


@router.patch("/admin-accounts/{account_id}")
async def admin_account_update(
    request: Request,
    account_id: int,
    username: str = Form(...),
    email: str = Form(...),
    display_name: str | None = Form(default=None),
    role: str = Form(...),
    current_user=Depends(require_admin_user),
    admin_accounts_service: AdminAccountsService = Depends(get_admin_accounts_service),
    session_store=Depends(get_session_store),
):
    try:
        role_value = UserRole(role)
        admin_account = await admin_accounts_service.update_admin_account(
            user_account_id=account_id,
            username=username,
            email=email,
            display_name=display_name,
            role=role_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role.") from exc
    if admin_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin account not found.")
    session = getattr(request.state, "session", None)
    if session is not None and current_user.user_account_id == account_id:
        session_store.invalidate_session_cache(session.session_id)
    return redirect_to(f"/admin-accounts/{account_id}")


@router.post("/admin-accounts/{account_id}/impersonate")
async def admin_account_impersonate(
    request: Request,
    account_id: int,
    current_user=Depends(require_admin_user),
    admin_accounts_service: AdminAccountsService = Depends(get_admin_accounts_service),
    session_cookie_signer: SessionCookieSigner = Depends(get_session_cookie_signer),
    settings=Depends(get_settings),
    session_store=Depends(get_session_store),
):
    if current_user.user_account_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin account not found.")
    if current_user.user_account_id == account_id:
        return redirect_to(f"/admin-accounts/{account_id}")
    admin_account = await admin_accounts_service.get_admin_account_detail(account_id)
    if admin_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin account not found.")

    new_session = await session_store.create_session(
        auth_user_id=admin_account.auth_user_id,
        user_account_id=admin_account.user_account_id,
        impersonator_auth_user_id=current_user.auth_user_id,
        impersonator_user_account_id=current_user.user_account_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    previous_session = getattr(request.state, "session", None)
    if previous_session is not None:
        await session_store.delete_session(previous_session.session_id)

    log_admin_activity(
        request=request,
        user=current_user,
        action="admin_account.start_impersonation",
        subject_type="admin_account",
        subject_id=account_id,
        details={"impersonated_user_account_id": account_id},
    )
    response = redirect_to("/")
    _set_session_cookie(
        response,
        request=request,
        settings=settings,
        session_cookie_signer=session_cookie_signer,
        session_id=new_session.session_id,
    )
    return response


@router.post("/mobile-card-april-state")
async def mobile_card_april_state_update(
    request: Request,
    enabled: str = Form(...),
    current_user=Depends(require_admin_user),
    mobile_card_april_state_service: MobileCardAprilStateService = Depends(
        get_mobile_card_april_state_service
    ),
):
    if current_user.email.strip().lower() != _APRIL_TOGGLE_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is required.",
        )
    normalized_enabled = enabled.strip().lower()
    if normalized_enabled not in {"true", "false"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid enabled value.",
        )
    target_enabled = normalized_enabled == "true"
    await mobile_card_april_state_service.set_enabled(
        enabled=target_enabled,
        updated_by_user_account_id=current_user.user_account_id,
    )
    log_admin_activity(
        request=request,
        user=current_user,
        action="mobile_card_april_state.update",
        subject_type="mobile_card_april_state",
        details={"enabled": target_enabled},
    )
    message = (
        "Aprilspøken ble aktivert."
        if target_enabled
        else "Aprilspøken ble deaktivert."
    )
    return redirect_to(f"/?mobile_card_april_message={quote_plus(message)}")


@router.delete("/admin-accounts/{account_id}")
async def admin_account_delete(
    request: Request,
    account_id: int,
    current_user=Depends(require_admin_user),
    admin_accounts_service: AdminAccountsService = Depends(get_admin_accounts_service),
    supabase_auth_gateway=Depends(get_supabase_auth_gateway),
):
    if current_user.user_account_id == account_id:
        return _redirect_with_error(f"/admin-accounts/{account_id}", "Du kan ikke slette din egen admin-konto.")

    admin_account = await admin_accounts_service.get_admin_account_detail(account_id)
    if admin_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin account not found.")

    try:
        await supabase_auth_gateway.delete_user(admin_account.auth_user_id)
        await admin_accounts_service.delete_admin_account(
            user_account_id=admin_account.user_account_id,
            auth_user_id=admin_account.auth_user_id,
        )
    except Exception as exc:
        return _redirect_with_error(f"/admin-accounts/{account_id}", str(exc))

    log_admin_activity(
        request=request,
        user=current_user,
        action="admin_account.delete",
        subject_type="admin_account",
        subject_id=account_id,
    )
    return redirect_to("/admin-accounts")
