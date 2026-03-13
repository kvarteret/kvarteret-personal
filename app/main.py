from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.auth.cookies import unsign_session_id
from app.auth.session_store import get_session_store
from app.api.router import api_router
from app.web.router import web_router
from app.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Kvarteret Personal")
    app.state.settings = get_settings()
    app.state.session_store = get_session_store()
    app.state.login_service = None
    app.state.people_service = None
    app.state.groups_service = None
    app.state.courses_service = None
    app.state.search_service = None
    app.state.users_service = None
    app.state.mobile_card_service = None
    app.state.registrations_service = None
    app.state.semester_transfer_service = None
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    @app.middleware("http")
    async def load_current_user(request: Request, call_next):
        request.state.current_user = None
        request.state.session = None
        cookie_name = request.app.state.settings.session_cookie_name
        signed_cookie = request.cookies.get(cookie_name)
        if signed_cookie:
            try:
                session_id = unsign_session_id(signed_cookie)
                auth_context = await request.app.state.session_store.load_authenticated_user(session_id)
                if auth_context:
                    request.state.session, request.state.current_user = auth_context
            except Exception:
                request.state.current_user = None
                request.state.session = None
        response = await call_next(request)
        return response

    app.include_router(api_router)
    app.include_router(web_router)
    return app
