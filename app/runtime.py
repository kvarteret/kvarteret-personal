from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import cast

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.cookies import SessionCookieSigner
from app.auth.login_service import LoginService
from app.auth.repository import DatabaseAuthRepository
from app.auth.session_store import (
    SessionRepositoryProtocol,
    SessionStore,
    SessionStoreProtocol,
)
from app.auth.supabase_auth import SupabaseAuthGateway, SupabaseAuthGatewayProtocol
from app.config import Settings, get_settings, validate_production_secrets
from app.db.session import DatabaseRuntimeManager
from app.errors import NotConfiguredError
from app.media_tokens import MediaTokenService
from app.infrastructure.email.applicant_templates import ApplicantEmailTemplateRenderer
from app.infrastructure.email.mobile_card_templates import (
    MobileCardEmailTemplateRenderer,
)
from app.infrastructure.email.smtp import SmtpEmailSender
from app.infrastructure.email.protocols import EmailSenderProtocol
from app.domain.feedback.service import FeedbackService
from app.domain.mobile_card.repository import MobileCardRepository
from app.domain.mobile_card.april_state import (
    MobileCardAprilStateRepository,
    MobileCardAprilStateService,
)
from app.domain.spotify.repository import IntegrationTokensRepository
from app.domain.spotify.now_playing import NowPlayingService
from app.domain.volunteers.repository import VolunteersRepository
from app.domain.volunteer_applications.repository import VolunteerApplicationsRepository
from app.domain.courses.service import CoursesService
from app.domain.groups.service import GroupsService
from app.domain.mobile_card.service import MobileCardService
from app.domain.volunteers.service import VolunteersService
from app.domain.volunteer_applications.service import VolunteerApplicationsService
from app.domain.search import VolunteerSearchRepository, VolunteerSearchService
from app.domain.volunteers.semester_transfer import SemesterTransferService
from app.infrastructure.storage.service import StorageService
from app.domain.admin_accounts.service import AdminAccountsService
from app.events import SimpleEventBus

# Keep the app bootable in local and test environments that do not have live
# Supabase credentials, while still failing fast once a protected auth path is used.
class UnconfiguredSupabaseAuthGateway(SupabaseAuthGatewayProtocol):
    _MISSING_CREDENTIALS = "Supabase credentials are required for authentication."

    async def sign_in_with_password(self, email: str, password: str):
        raise NotConfiguredError(self._MISSING_CREDENTIALS)

    async def create_user(
        self, *, email: str, password: str, metadata: dict | None = None
    ):
        raise NotConfiguredError(self._MISSING_CREDENTIALS)

    async def invite_user(
        self,
        *,
        email: str,
        metadata: dict | None = None,
        redirect_to: str | None = None,
    ):
        raise NotConfiguredError(self._MISSING_CREDENTIALS)

    async def generate_link(
        self,
        *,
        link_type: str,
        email: str,
        redirect_to: str | None = None,
        metadata: dict | None = None,
    ):
        raise NotConfiguredError(self._MISSING_CREDENTIALS)

    async def update_user_password(self, auth_user_id, password: str):
        raise NotConfiguredError(self._MISSING_CREDENTIALS)

    async def update_password_with_access_token(self, access_token: str, password: str):
        raise NotConfiguredError(self._MISSING_CREDENTIALS)

    async def delete_user(self, auth_user_id):
        raise NotConfiguredError(self._MISSING_CREDENTIALS)

    async def aclose(self) -> None:
        return None


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    database_runtime_manager: DatabaseRuntimeManager
    session_factory: async_sessionmaker[AsyncSession]
    session_cookie_signer: SessionCookieSigner
    media_token_service: MediaTokenService
    auth_repository: DatabaseAuthRepository
    session_store: SessionStoreProtocol
    storage_service: StorageService | None
    email_sender: EmailSenderProtocol
    supabase_auth_gateway: SupabaseAuthGatewayProtocol
    login_service: LoginService
    volunteers_service: VolunteersService
    groups_service: GroupsService
    courses_service: CoursesService
    volunteer_search_service: VolunteerSearchService
    admin_accounts_service: AdminAccountsService
    mobile_card_service: MobileCardService
    mobile_card_april_state_service: MobileCardAprilStateService
    now_playing_service: NowPlayingService
    volunteer_applications_service: VolunteerApplicationsService
    semester_transfer_service: SemesterTransferService
    feedback_service: FeedbackService
    event_bus: SimpleEventBus

    async def aclose(self) -> None:
        if self.storage_service is not None:
            self.storage_service.close()
        await self.now_playing_service.aclose()
        await self.supabase_auth_gateway.aclose()
        await self.database_runtime_manager.aclose()


# Centralize the object graph here so the app, tests, and one-off scripts can
# swap an entire runtime configuration by replacing a single container object.
def build_application_container(
    settings: Settings | None = None,
) -> ApplicationContainer:
    resolved_settings = validate_production_secrets(settings or get_settings())
    database_runtime_manager = DatabaseRuntimeManager(resolved_settings)
    session_factory = database_runtime_manager.get_session_factory()
    session_cookie_signer = SessionCookieSigner(resolved_settings)
    media_token_service = MediaTokenService(resolved_settings)
    auth_repository = DatabaseAuthRepository(session_factory=session_factory)
    session_store = SessionStore(
        cast(SessionRepositoryProtocol, auth_repository), resolved_settings
    )
    storage_service = _build_storage_service(resolved_settings)
    supabase_auth_gateway = _build_supabase_auth_gateway(resolved_settings)
    email_sender = SmtpEmailSender(resolved_settings)
    mobile_card_email_renderer = MobileCardEmailTemplateRenderer()
    applicant_email_renderer = ApplicantEmailTemplateRenderer()
    event_bus = SimpleEventBus()
    mobile_card_april_state_service = MobileCardAprilStateService(
        repository=MobileCardAprilStateRepository(session_factory=session_factory)
    )

    container = ApplicationContainer(
        settings=resolved_settings,
        database_runtime_manager=database_runtime_manager,
        session_factory=session_factory,
        session_cookie_signer=session_cookie_signer,
        media_token_service=media_token_service,
        auth_repository=auth_repository,
        session_store=session_store,
        storage_service=storage_service,
        email_sender=email_sender,
        supabase_auth_gateway=supabase_auth_gateway,
        login_service=LoginService(
            repository=auth_repository,
            supabase_auth=supabase_auth_gateway,
            session_store=session_store,
        ),
        volunteers_service=VolunteersService(
            repository=VolunteersRepository(session_factory=session_factory),
            storage_service=storage_service,
            media_token_service=media_token_service,
            detail_cache_ttl_seconds=resolved_settings.volunteer_detail_cache_ttl_seconds,
            photo_upload_max_bytes=resolved_settings.photo_upload_max_bytes,
            photo_max_dimension=resolved_settings.photo_max_dimension,
        ),
        groups_service=GroupsService(session_factory=session_factory),
        courses_service=CoursesService(session_factory=session_factory),
        volunteer_search_service=VolunteerSearchService(
            VolunteerSearchRepository(session_factory=session_factory)
        ),
        admin_accounts_service=AdminAccountsService(
            session_factory=session_factory,
            cache_ttl_seconds=resolved_settings.admin_accounts_cache_ttl_seconds,
        ),
        mobile_card_april_state_service=mobile_card_april_state_service,
        mobile_card_service=MobileCardService(
            resolved_settings,
            repository=MobileCardRepository(session_factory=session_factory),
            email_sender=email_sender,
            media_token_service=media_token_service,
            april_state_service=mobile_card_april_state_service,
            email_template_renderer=mobile_card_email_renderer,
        ),
        now_playing_service=NowPlayingService(
            resolved_settings,
            repository=IntegrationTokensRepository(session_factory=session_factory),
        ),
        volunteer_applications_service=VolunteerApplicationsService(
            settings=resolved_settings,
            repository=VolunteerApplicationsRepository(
                session_factory=session_factory,
                media_token_service=media_token_service,
            ),
            email_sender=email_sender,
            applicant_email_renderer=applicant_email_renderer,
            storage_service=storage_service,
            pending_count_cache_ttl_seconds=resolved_settings.pending_volunteer_applications_cache_ttl_seconds,
        ),
        semester_transfer_service=SemesterTransferService(
            session_factory=session_factory
        ),
        feedback_service=FeedbackService(resolved_settings),
        event_bus=event_bus,
    )

    return container


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    if not hasattr(app.state, "container"):
        app.state.container = build_application_container()
    try:
        yield
    finally:
        await app.state.container.aclose()


def _build_storage_service(settings: Settings) -> StorageService | None:
    if not settings.azure_blob_connection_string:
        return None
    return StorageService(settings)


def _build_supabase_auth_gateway(settings: Settings) -> SupabaseAuthGatewayProtocol:
    if not settings.supabase_url or not settings.supabase_secret_key:
        return UnconfiguredSupabaseAuthGateway()
    return SupabaseAuthGateway(settings)
