from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse

from app.auth.roles import UserRole
from app.auth.cookies import SessionCookieSigner
from app.auth.login_service import LoginError, LoginService
from app.dependencies import (
    get_current_user,
    get_login_service,
    get_session_cookie_signer,
    get_session_store,
    get_settings,
)
from app.errors import NotConfiguredError
from app.observability import log_admin_activity
from app.web.templates import templates

router = APIRouter()


@router.get("/")
async def dashboard(
    request: Request,
    current_user=Depends(get_current_user),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "pages/dashboard.html",
        {
            "title": "Kvarteret Personal",
            "section": "dashboard",
            "current_user": current_user,
        },
    )


@router.get("/login")
async def login_page(
    request: Request,
    current_user=Depends(get_current_user),
):
    if current_user is not None:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "pages/login.html",
        {
            "title": "Login",
            "section": "login",
            "error_message": None,
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
):
    try:
        result = await login_service.login_with_bridge(
            identifier=identifier,
            password=password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except NotConfiguredError:
        return templates.TemplateResponse(
            request,
            "pages/login.html",
            {
                "title": "Login",
                "section": "login",
                "error_message": "Login is not configured yet.",
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except LoginError:
        return templates.TemplateResponse(
            request,
            "pages/login.html",
            {
                "title": "Login",
                "section": "login",
                "error_message": "Invalid credentials.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_cookie_signer.sign_session_id(result.session.session_id),
        httponly=True,
        secure=request.url.scheme == "https" or settings.app_env == "production",
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
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
        except Exception:
            pass
    if current_user is not None and current_user.role == UserRole.ADMIN:
        log_admin_activity(
            request=request,
            user=current_user,
            action="logout",
            subject_type="session",
            subject_id=getattr(getattr(request.state, "session", None), "session_id", None),
        )
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(settings.session_cookie_name)
    return response
