import logging
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.auth.cookies import unsign_session_id
from app.api.router import api_router
from app.dependencies import get_volunteer_applications_service, get_session_store, get_settings
from app.media.router import router as media_router
from app.observability import (
    bind_request_context,
    build_request_id,
    clear_request_context,
    client_ip_from_request,
    configure_logging,
    log_request,
    log_request_exception,
    request_context_for_user,
    reset_request_context,
)
from app.runtime import app_lifespan, build_application_container
from app.system.router import router as system_router
from app.web.router import web_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    container = build_application_container()
    configure_logging(container.settings)
    app = FastAPI(title="Kvarteret Personal", lifespan=app_lifespan)
    app.state.container = container
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    @app.middleware("http")
    async def method_override(request: Request, call_next):
        if request.method == "POST":
            override = request.query_params.get("_method") or request.headers.get("X-HTTP-Method-Override")
            if override:
                request.scope["method"] = override.upper()
        return await call_next(request)

    @app.middleware("http")
    async def load_current_user(request: Request, call_next):
        started_at = perf_counter()
        request_id = build_request_id(request)
        token = bind_request_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=client_ip_from_request(request),
        )
        request.state.current_user = None
        request.state.session = None
        request.state.volunteer_application_pending_count = 0
        settings_override = request.app.dependency_overrides.get(get_settings)
        session_store_override = request.app.dependency_overrides.get(get_session_store)
        settings = _resolve_override(settings_override, request, request.app.state.container.settings)
        session_store = _resolve_override(session_store_override, request, request.app.state.container.session_store)
        cookie_name = settings.session_cookie_name
        signed_cookie = request.cookies.get(cookie_name)
        if signed_cookie:
            try:
                session_id = unsign_session_id(signed_cookie)
                auth_context = await session_store.load_authenticated_user(session_id)
                if auth_context:
                    request.state.session, request.state.current_user = auth_context
                    bind_request_context(**request_context_for_user(request.state.current_user))
                    if request.state.current_user.role == "Admin":
                        volunteer_applications_service_override = request.app.dependency_overrides.get(get_volunteer_applications_service)
                        volunteer_applications_service = _resolve_override(
                            volunteer_applications_service_override,
                            request,
                            request.app.state.container.volunteer_applications_service,
                        )
                        try:
                            request.state.volunteer_application_pending_count = (
                                await volunteer_applications_service.count_pending_volunteer_applications()
                            )
                        except Exception:
                            request.state.volunteer_application_pending_count = 0
            except Exception:
                request.state.current_user = None
                request.state.session = None
        try:
            response = await call_next(request)
        except Exception:
            log_request_exception(logger, request=request, started_at=started_at)
            raise
        finally:
            if "response" in locals():
                _apply_html_preload_cache_headers(request, response)
                response.headers["X-Request-ID"] = request_id
                log_request(logger, request=request, status_code=response.status_code, started_at=started_at)
            reset_request_context(token)
            clear_request_context()
        return response

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException):
        if exc.status_code == 401 and _is_web_navigation_request(request):
            if request.headers.get("HX-Request") == "true":
                return Response(status_code=200, headers={"HX-Redirect": "/login"})
            return RedirectResponse(url="/login", status_code=303)
        return await http_exception_handler(request, exc)

    app.include_router(system_router)
    app.include_router(media_router)
    app.include_router(api_router)
    app.include_router(web_router)
    return app


def _resolve_override(provider, request: Request, fallback):
    if provider is None:
        return fallback
    try:
        return provider(request)
    except TypeError:
        return provider()


def _apply_html_preload_cache_headers(request: Request, response) -> None:
    if request.method != "GET" or response.status_code != 200:
        return
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("text/html"):
        return
    if response.headers.get("Cache-Control"):
        _merge_vary_headers(response, "Cookie", "HX-Boosted", "HX-Request")
        return
    response.headers["Cache-Control"] = "private, max-age=60"
    _merge_vary_headers(response, "Cookie", "HX-Boosted", "HX-Request")


def _merge_vary_headers(response, *values: str) -> None:
    existing = response.headers.get("Vary", "")
    merged = {value.strip() for value in existing.split(",") if value.strip()}
    merged.update(values)
    response.headers["Vary"] = ", ".join(sorted(merged))


def _is_web_navigation_request(request: Request) -> bool:
    path = request.url.path
    return not path.startswith("/api/")
