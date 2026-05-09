from fastapi import APIRouter

from app.api.now_playing import router as now_playing_router
from app.api.legacy.mobile_card import router as legacy_mobile_card_router
from app.api.v1.events import router as events_router
from app.api.v1.mobile_card import router as mobile_card_router
from app.api.v1.stats import router as stats_router
from app.api.v1.volunteer_prospects import router as volunteer_prospects_router

api_router = APIRouter()
api_router.include_router(now_playing_router, prefix="/api", tags=["now-playing"])
api_router.include_router(events_router, prefix="/api/v1/events", tags=["events"])
api_router.include_router(
    mobile_card_router, prefix="/api/v1/mobile-card", tags=["mobile-card"]
)
api_router.include_router(
    volunteer_prospects_router,
    prefix="/api/v1/volunteer-prospects",
    tags=["volunteer-prospects"],
)
api_router.include_router(stats_router, prefix="/api/v1/stats", tags=["stats"])
api_router.include_router(
    legacy_mobile_card_router,
    prefix="/api/DigitalInternkort",
    tags=["legacy-mobile-card"],
)
