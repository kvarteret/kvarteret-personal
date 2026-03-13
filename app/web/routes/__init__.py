from fastapi import APIRouter

from app.web.routes.auth import router as auth_router
from app.web.routes.courses import router as courses_router
from app.web.routes.groups import router as groups_router
from app.web.routes.people import router as people_router
from app.web.routes.registrations import router as registrations_router
from app.web.routes.search import router as search_router
from app.web.routes.users import router as users_router

web_router = APIRouter()
web_router.include_router(auth_router)
web_router.include_router(people_router)
web_router.include_router(groups_router)
web_router.include_router(courses_router)
web_router.include_router(search_router)
web_router.include_router(users_router)
web_router.include_router(registrations_router)
