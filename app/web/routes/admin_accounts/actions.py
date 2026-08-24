from __future__ import annotations

import logging
import secrets
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
from app.errors import NotConfiguredError
from app.web.route_helpers import redirect_to

_ADMIN_ACCESS_REQUIRED = "Admin access is required."
_ADMIN_ACCOUNT_NOT_FOUND = "Admin account not found."
_INVALID_ROLE = "Invalid role."
_ADMIN_ACCOUNTS_NEW_PATH = "/admin-accounts/new"

router = APIRouter()
_APRIL_TOGGLE_EMAIL = "it.leder@kvarteret.no"
logger = logging.getLogger(__name__)


def _redirect_with_error(path: str, message: str):
    separator = "&" if "?" in path else "?"
    return redirect_to(f"{path}{separator}error={quote_plus(message)}")


def _redirect_with_password_error(message: str):
    return redirect_to(f"/my-account?password_error={quote_plus(message)}")


async def _best_effort_delete_auth_user(
    auth_gateway, auth_user_id, *, context: str
) -> None:
    try:
        await auth_gateway.delete_user(auth_user_id)
    except Exception:
        logger.exception("Failed to clean up auth user after %s.", context)


async def _best_effort_delete_admin_account(
    admin_accounts_service, *, user_account_id: int, auth_user_id, context: str
) -> None:
    try:
        await admin_accounts_service.delete_admin_account(
            user_account_id=user_account_id,
            auth_user_id=auth_user_id,
        )
    except Exception:
        logger.exception("Failed to clean up admin account after %s.", context)


async def _cleanup_failed_admin_creation(
    admin_accounts_service: AdminAccountsService,
    supabase_auth_gateway,
    *,
    admin_account,
    auth_user_id: str | None,
    auth_user_created: bool,
    context: str,
) -> None:
    if admin_account is not None:
        await _best_effort_delete_admin_account(
            admin_accounts_service,
            user_account_id=admin_account.user_account_id,
            auth_user_id=admin_account.auth_user_id,
            context=context,
        )
    if auth_user_id is not None and auth_user_created:
        await _best_effort_delete_auth_user(
            supabase_auth_gateway,
            auth_user_id,
            context=context,
        )


def _build_onboarding_redirect_url(request: Request, base_url: str | None) -> str:
    if base_url:
        origin = base_url.rstrip("/")
    else:
        origin = str(request.base_url).rstrip("/")
    return f"{origin}/set-password"


def _set_session_cookie(
    response,
    *,
    request: Request,
    settings,
    session_cookie_signer: SessionCookieSigner,
    session_id: str,
) -> None:
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=_ADMIN_ACCESS_REQUIRED
        )
    if current_user.user_account_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_ADMIN_ACCOUNT_NOT_FOUND
        )
    try:
        role_value = UserRole(role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=_INVALID_ROLE
        ) from exc
    try:
        admin_account = await admin_accounts_service.update_admin_account(
            user_account_id=current_user.user_account_id,
            username=username,
            email=email,
            display_name=display_name,
            role=role_value,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if admin_account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_ADMIN_ACCOUNT_NOT_FOUND
        )
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=_ADMIN_ACCESS_REQUIRED
        )
    if len(new_password) < 8:
        return _redirect_with_password_error("Det nye passordet må være minst 8 tegn.")
    if new_password != confirm_password:
        return _redirect_with_password_error("Passordene må være like.")
    try:
        verified_auth_user_id = await supabase_auth_gateway.sign_in_with_password(
            current_user.email, current_password
        )
    except Exception:
        logger.exception("Failed to verify admin password change request.")
        return _redirect_with_password_error(
            "Kunne ikke oppdatere passordet akkurat nå."
        )
    if verified_auth_user_id != current_user.auth_user_id:
        return _redirect_with_password_error("Nåværende passord er feil.")
    try:
        await supabase_auth_gateway.update_user_password(
            current_user.auth_user_id, new_password
        )
    except Exception:
        logger.exception("Failed to update admin password.")
        return _redirect_with_password_error(
            "Kunne ikke oppdatere passordet akkurat nå."
        )
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
    settings=Depends(get_settings),
    supabase_auth_gateway=Depends(get_supabase_auth_gateway),
):
    try:
        role_value = UserRole(role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=_INVALID_ROLE
        ) from exc

    auth_user_id = None
    auth_user_created = False
    admin_account = None
    setup_url = None
    try:
        normalized_username = username.strip()
        normalized_display_name = (
            display_name.strip() if display_name and display_name.strip() else None
        )
        normalized_email = email.strip().lower()
        auth_user_id = await supabase_auth_gateway.find_user_id_by_email(
            normalized_email
        )
        if auth_user_id is None:
            try:
                auth_user_id = await supabase_auth_gateway.create_user(
                    email=normalized_email,
                    password=secrets.token_urlsafe(24),
                    metadata={
                        "username": normalized_username,
                        "display_name": normalized_display_name,
                        "role": role_value.value,
                    },
                )
                auth_user_created = True
            except Exception:
                # Another request may have created the Auth identity between
                # the lookup and create call. Reconcile before surfacing a
                # provider error, and never delete that pre-existing identity.
                auth_user_id = await supabase_auth_gateway.find_user_id_by_email(
                    normalized_email
                )
                if auth_user_id is None:
                    raise
        admin_account = await admin_accounts_service.create_admin_account(
            auth_user_id=auth_user_id,
            username=username,
            email=normalized_email,
            display_name=display_name,
            role=role_value,
        )
        setup_url = await supabase_auth_gateway.generate_link(
            link_type="recovery",
            email=normalized_email,
            redirect_to=_build_onboarding_redirect_url(
                request, settings.app_public_base_url
            ),
        )
        await admin_accounts_service.send_onboarding_email(
            recipient_email=normalized_email,
            setup_url=setup_url,
            display_name=normalized_display_name,
            username=normalized_username,
            role_name=role_value.value,
        )
    except NotConfiguredError as exc:
        await _cleanup_failed_admin_creation(
            admin_accounts_service,
            supabase_auth_gateway,
            admin_account=admin_account,
            auth_user_id=auth_user_id,
            auth_user_created=auth_user_created,
            context="admin onboarding configuration failure",
        )
        return _redirect_with_error(_ADMIN_ACCOUNTS_NEW_PATH, str(exc))
    except ValueError as exc:
        await _cleanup_failed_admin_creation(
            admin_accounts_service,
            supabase_auth_gateway,
            admin_account=admin_account,
            auth_user_id=auth_user_id,
            auth_user_created=auth_user_created,
            context="admin-account validation failure",
        )
        return _redirect_with_error(_ADMIN_ACCOUNTS_NEW_PATH, str(exc))
    except Exception:
        if admin_account is not None:
            await _best_effort_delete_admin_account(
                admin_accounts_service,
                user_account_id=admin_account.user_account_id,
                auth_user_id=admin_account.auth_user_id,
                context="admin-account creation failure",
            )
        if auth_user_id is not None and auth_user_created:
            await _best_effort_delete_auth_user(
                supabase_auth_gateway,
                auth_user_id,
                context="admin-account creation failure",
            )
        logger.exception("Failed to create admin account.")
        return _redirect_with_error(
            _ADMIN_ACCOUNTS_NEW_PATH,
            "Kunne ikke opprette admin-kontoen akkurat nå.",
        )

    log_admin_activity(
        request=request,
        user=current_user,
        action="admin_account.create",
        subject_type="admin_account",
        subject_id=admin_account.user_account_id,
        details={
            "role": admin_account.role.value,
            "delivery": "smtp_onboarding_email",
            "setup_url": bool(setup_url),
        },
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
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=_INVALID_ROLE
        ) from exc
    try:
        admin_account = await admin_accounts_service.update_admin_account(
            user_account_id=account_id,
            username=username,
            email=email,
            display_name=display_name,
            role=role_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if admin_account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_ADMIN_ACCOUNT_NOT_FOUND
        )
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_ADMIN_ACCOUNT_NOT_FOUND
        )
    if current_user.user_account_id == account_id:
        return redirect_to(f"/admin-accounts/{account_id}")
    admin_account = await admin_accounts_service.get_admin_account_detail(account_id)
    if admin_account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_ADMIN_ACCOUNT_NOT_FOUND
        )

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
            detail=_ADMIN_ACCESS_REQUIRED,
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
        "Aprilspøken ble aktivert." if target_enabled else "Aprilspøken ble deaktivert."
    )
    return redirect_to(f"/?mobile_card_april_message={quote_plus(message)}")


@router.delete("/admin-accounts/{account_id}")
async def admin_account_delete(
    request: Request,
    account_id: int,
    current_user=Depends(require_admin_user),
    admin_accounts_service: AdminAccountsService = Depends(get_admin_accounts_service),
):
    if current_user.user_account_id == account_id:
        return _redirect_with_error(
            f"/admin-accounts/{account_id}", "Du kan ikke slette din egen admin-konto."
        )

    admin_account = await admin_accounts_service.get_admin_account_detail(account_id)
    if admin_account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_ADMIN_ACCOUNT_NOT_FOUND
        )

    try:
        await admin_accounts_service.delete_admin_account(
            user_account_id=admin_account.user_account_id,
            auth_user_id=admin_account.auth_user_id,
        )
    except Exception:
        logger.exception("Failed to delete admin account %s.", account_id)
        return _redirect_with_error(
            f"/admin-accounts/{account_id}",
            "Kunne ikke slette admin-kontoen akkurat nå.",
        )

    log_admin_activity(
        request=request,
        user=current_user,
        action="admin_account.delete",
        subject_type="admin_account",
        subject_id=account_id,
    )
    return redirect_to("/admin-accounts")
