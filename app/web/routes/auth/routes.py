from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature

from app.auth.roles import UserRole
from app.auth.cookies import SessionCookieSigner
from app.auth.login_service import LoginError, LoginService
from app.db.rate_limit import RateLimiter, RateLimitExceeded
from app.dependencies import (
    get_current_user,
    get_login_service,
    get_mobile_card_april_state_service,
    get_rate_limiter,
    get_session_cookie_signer,
    get_session_store,
    get_settings,
    get_supabase_auth_gateway,
    require_authenticated_user,
)
from app.observability import client_ip_from_request
from app.errors import NotConfiguredError
from app.observability import log_admin_activity
from app.domain.mobile_card.april_state import MobileCardAprilStateService
from app.web.templates import templates

_LOGIN_TEMPLATE = "pages/auth/login.html"

router = APIRouter()
_APRIL_TOGGLE_EMAIL = "it.leder@kvarteret.no"
logger = logging.getLogger(__name__)


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


@router.get("/")
async def dashboard(
    request: Request,
    mobile_card_april_message: str | None = None,
    current_user=Depends(get_current_user),
    mobile_card_april_state_service: MobileCardAprilStateService = Depends(
        get_mobile_card_april_state_service
    ),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    show_mobile_card_april_toggle = (
        current_user.role == UserRole.ADMIN
        and current_user.email.strip().lower() == _APRIL_TOGGLE_EMAIL
    )
    mobile_card_april_enabled = False
    if show_mobile_card_april_toggle:
        mobile_card_april_enabled = await mobile_card_april_state_service.is_enabled()
    return templates.TemplateResponse(
        request,
        "pages/auth/dashboard.html",
        {
            "title": "Kvarteret Personal",
            "section": "dashboard",
            "current_user": current_user,
            "mobile_card_april_enabled": mobile_card_april_enabled,
            "mobile_card_april_message": mobile_card_april_message,
            "show_mobile_card_april_toggle": show_mobile_card_april_toggle,
        },
    )


@router.get("/login")
async def login_page(
    request: Request,
    message: str | None = None,
    current_user=Depends(get_current_user),
):
    if current_user is not None:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        _LOGIN_TEMPLATE,
        {
            "title": "Login",
            "section": "login",
            "error_message": None,
            "message": message,
        },
    )


@router.post("/login")
async def login_submit(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    login_service: LoginService = Depends(get_login_service),
    session_cookie_signer: SessionCookieSigner = Depends(get_session_cookie_signer),
    settings=Depends(get_settings),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
):
    normalized_identifier = identifier.strip().lower()
    client_ip = client_ip_from_request(request)
    throttle_keys = [f"login:account:{normalized_identifier}"]
    if client_ip:
        throttle_keys.append(f"login:ip:{client_ip}")
    try:
        # Counted before verification so failures cannot race the check.
        for key in throttle_keys:
            await rate_limiter.hit(
                key,
                limit=settings.login_attempt_limit,
                window_seconds=settings.login_attempt_window_seconds,
            )
    except RateLimitExceeded:
        logger.warning(
            "login throttled",
            extra={
                "event": "auth.login.throttled",
                "event_data": {"identifier": normalized_identifier},
            },
        )
        return templates.TemplateResponse(
            request,
            _LOGIN_TEMPLATE,
            {
                "title": "Login",
                "section": "login",
                "error_message": "Too many login attempts. Try again later.",
                "message": None,
            },
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    try:
        result = await login_service.login(
            identifier=identifier,
            password=password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except NotConfiguredError:
        return templates.TemplateResponse(
            request,
            _LOGIN_TEMPLATE,
            {
                "title": "Login",
                "section": "login",
                "error_message": "Login is not configured yet.",
                "message": None,
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except LoginError:
        return templates.TemplateResponse(
            request,
            _LOGIN_TEMPLATE,
            {
                "title": "Login",
                "section": "login",
                "error_message": "Invalid credentials.",
                "message": None,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(
        response,
        request=request,
        settings=settings,
        session_cookie_signer=session_cookie_signer,
        session_id=result.session.session_id,
    )
    return response


@router.post("/logout")
async def logout(
    request: Request,
    current_user=Depends(get_current_user),
    session_cookie_signer: SessionCookieSigner = Depends(get_session_cookie_signer),
    settings=Depends(get_settings),
    session_store=Depends(get_session_store),
):
    signed_cookie = request.cookies.get(settings.session_cookie_name)
    if signed_cookie:
        try:
            session_id = session_cookie_signer.unsign_session_id(signed_cookie)
            await session_store.delete_session(session_id)
        except BadSignature:
            logger.warning("Discarded invalid session cookie during logout.")
        except Exception:
            logger.exception("Failed to revoke session during logout.")
    if current_user is not None and current_user.role == UserRole.ADMIN:
        log_admin_activity(
            request=request,
            user=current_user,
            action="logout",
            subject_type="session",
            subject_id=getattr(
                getattr(request.state, "session", None), "session_id", None
            ),
        )
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(settings.session_cookie_name)
    return response


@router.get("/set-password")
async def set_password_page(
    request: Request,
    error: str | None = None,
):
    return templates.TemplateResponse(
        request,
        "pages/auth/set_password.html",
        {
            "title": "Set Password",
            "section": "set-password",
            "error_message": error,
            "access_token": None,
        },
    )


@router.post("/set-password")
async def set_password_submit(
    request: Request,
    access_token: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    supabase_auth_gateway=Depends(get_supabase_auth_gateway),
):
    error_message = None
    normalized_access_token = access_token.strip()
    if not normalized_access_token:
        error_message = "Password setup link is missing or invalid."
    elif len(password) < 8:
        error_message = "Passordet må være minst 8 tegn."
    elif password != confirm_password:
        error_message = "Passordene må være like."
    else:
        try:
            await supabase_auth_gateway.update_password_with_access_token(
                normalized_access_token, password
            )
        except Exception:
            logger.exception("Failed to set password from onboarding link.")
            error_message = "Kunne ikke sette passordet akkurat nå."
    if error_message is not None:
        return templates.TemplateResponse(
            request,
            "pages/auth/set_password.html",
            {
                "title": "Set Password",
                "section": "set-password",
                "error_message": error_message,
                "access_token": normalized_access_token,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(
        url="/login?message=Passordet+er+satt.+Du+kan+logge+inn+na.",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/impersonation/stop")
async def stop_impersonation(
    request: Request,
    current_user=Depends(require_authenticated_user),
    session_cookie_signer: SessionCookieSigner = Depends(get_session_cookie_signer),
    settings=Depends(get_settings),
    session_store=Depends(get_session_store),
):
    session = getattr(request.state, "session", None)
    impersonator_user = getattr(session, "impersonator_user", None)
    if session is None or impersonator_user is None:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    new_session = await session_store.create_session(
        auth_user_id=impersonator_user.auth_user_id,
        user_account_id=impersonator_user.user_account_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await session_store.delete_session(session.session_id)
    log_admin_activity(
        request=request,
        user=impersonator_user,
        action="admin_account.stop_impersonation",
        subject_type="admin_account",
        subject_id=current_user.user_account_id,
        details={"impersonated_user_account_id": current_user.user_account_id},
    )
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(
        response,
        request=request,
        settings=settings,
        session_cookie_signer=session_cookie_signer,
        session_id=new_session.session_id,
    )
    return response
