from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from app.auth.login_service import LoginService
from app.auth.models import AuthenticatedUser, WebSession
from app.auth.roles import UserRole
from app.runtime import ApplicationContainer
from app.services.feedback import FeedbackService
from app.services.courses import CoursesService
from app.services.groups import GroupsService
from app.services.mobile_card import MobileCardService
from app.services.volunteers import VolunteersService
from app.services.volunteer_applications import VolunteerApplicationsService
from app.services.search import VolunteerSearchService
from app.services.semester_transfer import SemesterTransferService
from app.services.admin_accounts import AdminAccountsService


@dataclass(slots=True)
class RequestAuthContext:
    session: WebSession | None
    user: AuthenticatedUser | None


def get_container(request: Request) -> ApplicationContainer:
    return request.app.state.container


def get_settings(request: Request):
    return get_container(request).settings


def get_session_store(request: Request):
    return get_container(request).session_store


def get_request_auth_context(request: Request) -> RequestAuthContext:
    return RequestAuthContext(
        session=getattr(request.state, "session", None),
        user=getattr(request.state, "current_user", None),
    )


def get_current_user(request: Request) -> AuthenticatedUser | None:
    return getattr(request.state, "current_user", None)


def require_authenticated_user(
    current_user: AuthenticatedUser | None = Depends(get_current_user),
) -> AuthenticatedUser:
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return current_user


def require_admin_user(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> AuthenticatedUser:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Admin access is required."},
        )
    return current_user


def require_web_admin_user(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> AuthenticatedUser:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access is required.")
    return current_user


def get_login_service(request: Request) -> LoginService:
    return get_container(request).login_service


def get_supabase_auth_gateway(request: Request):
    return get_container(request).supabase_auth_gateway


def get_volunteers_service(request: Request) -> VolunteersService:
    return get_container(request).volunteers_service


def get_groups_service(request: Request) -> GroupsService:
    return get_container(request).groups_service


def get_courses_service(request: Request) -> CoursesService:
    return get_container(request).courses_service


def get_volunteer_search_service(request: Request) -> VolunteerSearchService:
    return get_container(request).volunteer_search_service


def get_admin_accounts_service(request: Request) -> AdminAccountsService:
    return get_container(request).admin_accounts_service


def get_mobile_card_service(request: Request) -> MobileCardService:
    return get_container(request).mobile_card_service


def get_volunteer_applications_service(request: Request) -> VolunteerApplicationsService:
    return get_container(request).volunteer_applications_service


def get_semester_transfer_service(request: Request) -> SemesterTransferService:
    return get_container(request).semester_transfer_service


def get_feedback_service(request: Request) -> FeedbackService:
    return get_container(request).feedback_service
