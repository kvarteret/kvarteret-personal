from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from app.auth.login_service import LoginService
from app.auth.repository import DatabaseAuthRepository
from app.auth.session_store import SessionStore
from app.auth.supabase_auth import SupabaseAuthGateway, SupabaseAuthGatewayProtocol
from app.config import Settings, get_settings
from app.db.session import dispose_database_runtime
from app.errors import NotConfiguredError
from app.services.feedback import FeedbackService
from app.services.mobile_card_repository import MobileCardRepository
from app.services.volunteers_repository import VolunteersRepository
from app.services.volunteer_applications_repository import VolunteerApplicationsRepository
from app.services.courses import CoursesService
from app.services.groups import GroupsService
from app.services.mobile_card import MobileCardService
from app.services.volunteers import VolunteersService
from app.services.volunteer_applications import VolunteerApplicationsService
from app.services.search import VolunteerSearchRepository, VolunteerSearchService
from app.services.semester_transfer import SemesterTransferService
from app.services.storage import StorageService
from app.services.admin_accounts import AdminAccountsService


class UnconfiguredSupabaseAuthGateway(SupabaseAuthGatewayProtocol):
    async def sign_in_with_password(self, email: str, password: str):
        raise NotConfiguredError("Supabase credentials are required for authentication.")

    async def create_user_from_legacy(self, legacy_user, password: str):
        raise NotConfiguredError("Supabase credentials are required for authentication.")

    async def create_user(self, *, email: str, password: str, metadata: dict | None = None):
        raise NotConfiguredError("Supabase credentials are required for authentication.")

    async def invite_user(self, *, email: str, metadata: dict | None = None, redirect_to: str | None = None):
        raise NotConfiguredError("Supabase credentials are required for authentication.")

    async def update_user_password(self, auth_user_id, password: str):
        raise NotConfiguredError("Supabase credentials are required for authentication.")

    async def delete_user(self, auth_user_id):
        raise NotConfiguredError("Supabase credentials are required for authentication.")

    def close(self) -> None:
        return None


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    auth_repository: DatabaseAuthRepository
    session_store: SessionStore
    storage_service: StorageService | None
    supabase_auth_gateway: SupabaseAuthGatewayProtocol
    login_service: LoginService
    volunteers_service: VolunteersService
    groups_service: GroupsService
    courses_service: CoursesService
    volunteer_search_service: VolunteerSearchService
    admin_accounts_service: AdminAccountsService
    mobile_card_service: MobileCardService
    volunteer_applications_service: VolunteerApplicationsService
    semester_transfer_service: SemesterTransferService
    feedback_service: FeedbackService

    async def aclose(self) -> None:
        if self.storage_service is not None:
            self.storage_service.close()
        self.supabase_auth_gateway.close()
        await dispose_database_runtime()


def build_application_container(settings: Settings | None = None) -> ApplicationContainer:
    resolved_settings = settings or get_settings()
    auth_repository = DatabaseAuthRepository()
    session_store = SessionStore(auth_repository, resolved_settings)
    storage_service = _build_storage_service(resolved_settings)
    supabase_auth_gateway = _build_supabase_auth_gateway(resolved_settings)

    return ApplicationContainer(
        settings=resolved_settings,
        auth_repository=auth_repository,
        session_store=session_store,
        storage_service=storage_service,
        supabase_auth_gateway=supabase_auth_gateway,
        login_service=LoginService(
            repository=auth_repository,
            supabase_auth=supabase_auth_gateway,
            session_store=session_store,
        ),
        volunteers_service=VolunteersService(
            repository=VolunteersRepository(),
            storage_service=storage_service,
        ),
        groups_service=GroupsService(),
        courses_service=CoursesService(),
        volunteer_search_service=VolunteerSearchService(VolunteerSearchRepository()),
        admin_accounts_service=AdminAccountsService(),
        mobile_card_service=MobileCardService(
            resolved_settings,
            repository=MobileCardRepository(),
        ),
        volunteer_applications_service=VolunteerApplicationsService(
            repository=VolunteerApplicationsRepository(),
            storage_service=storage_service,
        ),
        semester_transfer_service=SemesterTransferService(),
        feedback_service=FeedbackService(resolved_settings),
    )


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    if not hasattr(app.state, "container"):
        app.state.container = build_application_container()
    try:
        yield
    finally:
        await app.state.container.aclose()


def _build_storage_service(settings: Settings) -> StorageService | None:
    if not settings.supabase_url or not settings.supabase_secret_key:
        return None
    return StorageService(settings)


def _build_supabase_auth_gateway(settings: Settings) -> SupabaseAuthGatewayProtocol:
    if not settings.supabase_url or not settings.supabase_secret_key:
        return UnconfiguredSupabaseAuthGateway()
    return SupabaseAuthGateway(settings)
