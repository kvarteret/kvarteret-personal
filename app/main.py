import logging
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.auth.cookies import unsign_session_id
from app.api.router import api_router
from app.dependencies import get_session_store, get_settings
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
                response.headers["X-Request-ID"] = request_id
                log_request(logger, request=request, status_code=response.status_code, started_at=started_at)
            reset_request_context(token)
            clear_request_context()
        return response

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
