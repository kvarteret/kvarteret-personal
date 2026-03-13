from fastapi import APIRouter

from app.api.media import router as media_router
from app.api.v1.auth import router as auth_router
from app.api.v1.courses import router as courses_router
from app.api.v1.groups import router as groups_router
from app.api.legacy.mobile_card import router as legacy_mobile_card_router
from app.api.v1.mobile_card import router as mobile_card_router
from app.api.v1.people import router as people_router
from app.api.v1.registrations import router as registrations_router
from app.api.v1.search import router as search_router
from app.api.v1.system import router as system_router
from app.api.v1.users import router as users_router

api_router = APIRouter()
api_router.include_router(media_router, tags=["media"])
api_router.include_router(system_router, tags=["system"])
api_router.include_router(auth_router, prefix="/api/v1", tags=["auth"])
api_router.include_router(mobile_card_router, prefix="/api/v1/mobile-card", tags=["mobile-card"])
api_router.include_router(people_router, prefix="/api/v1", tags=["people"])
api_router.include_router(groups_router, prefix="/api/v1", tags=["groups"])
api_router.include_router(courses_router, prefix="/api/v1", tags=["courses"])
api_router.include_router(search_router, prefix="/api/v1", tags=["search"])
api_router.include_router(users_router, prefix="/api/v1", tags=["users"])
api_router.include_router(registrations_router, prefix="/api/v1", tags=["registrations"])
api_router.include_router(
    legacy_mobile_card_router,
    prefix="/api/DigitalInternkort",
    tags=["legacy-mobile-card"],
)
