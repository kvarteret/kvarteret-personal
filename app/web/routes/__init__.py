from fastapi import APIRouter, Depends

from app.dependencies import load_web_navigation_state

from app.web.routes.admin_account_actions import router as admin_account_actions_router
from app.web.routes.admin_account_pages import router as admin_account_pages_router
from app.web.routes.auth import router as auth_router
from app.web.routes.courses_actions import router as course_actions_router
from app.web.routes.courses_pages import router as course_pages_router
from app.web.routes.feedback import router as feedback_router
from app.web.routes.groups_actions import router as group_actions_router
from app.web.routes.groups_pages import router as group_pages_router
from app.web.routes.spotify_pages import router as spotify_pages_router
from app.web.routes.volunteer_actions import router as volunteer_actions_router
from app.web.routes.volunteer_application_actions import router as volunteer_application_actions_router
from app.web.routes.volunteer_application_pages import router as volunteer_application_pages_router
from app.web.routes.volunteer_fragments import router as volunteer_fragments_router
from app.web.routes.volunteer_pages import router as volunteer_pages_router
from app.web.routes.volunteer_search_fragments import router as volunteer_search_fragments_router
from app.web.routes.volunteer_search_pages import router as volunteer_search_pages_router

web_router = APIRouter(dependencies=[Depends(load_web_navigation_state)])
web_router.include_router(auth_router)
web_router.include_router(feedback_router)
web_router.include_router(volunteer_search_fragments_router)
web_router.include_router(volunteer_search_pages_router)
web_router.include_router(volunteer_fragments_router)
web_router.include_router(volunteer_actions_router)
web_router.include_router(volunteer_pages_router)
web_router.include_router(group_pages_router)
web_router.include_router(group_actions_router)
web_router.include_router(course_pages_router)
web_router.include_router(course_actions_router)
web_router.include_router(spotify_pages_router)
web_router.include_router(admin_account_pages_router)
web_router.include_router(admin_account_actions_router)
web_router.include_router(volunteer_application_pages_router)
web_router.include_router(volunteer_application_actions_router)
