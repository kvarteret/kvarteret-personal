from __future__ import annotations

from dataclasses import dataclass

from app.auth.models import AuthenticatedUser, WebSession
from app.auth.repository import AuthRepositoryProtocol
from app.auth.session_store import SessionStoreProtocol
from app.auth.supabase_auth import SupabaseAuthGatewayProtocol
from app.observability import get_domain_logger

logger = get_domain_logger(__name__)


class LoginError(Exception):
    """Raised when login fails."""


@dataclass(slots=True)
class LoginResult:
    session: WebSession
    user: AuthenticatedUser


class LoginService:
    def __init__(
        self,
        repository: AuthRepositoryProtocol,
        supabase_auth: SupabaseAuthGatewayProtocol,
        session_store: SessionStoreProtocol,
    ) -> None:
        self.repository = repository
        self.supabase_auth = supabase_auth
        self.session_store = session_store

    async def login(
        self,
        *,
        identifier: str,
        password: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> LoginResult:
        normalized_identifier = identifier.strip().lower()
        account = await self.repository.get_user_account_by_identifier(
            normalized_identifier
        )
        if account is None:
            logger.event(
                "auth.login.failed",
                fields={"reason_code": "account_not_found", "outcome": "failure"},
            )
            raise LoginError("Invalid credentials.")

        auth_user_id = await self.supabase_auth.sign_in_with_password(
            account.email, password
        )
        if auth_user_id is None:
            logger.event(
                "auth.login.failed",
                fields={"reason_code": "invalid_credentials", "outcome": "failure"},
            )
            raise LoginError("Invalid credentials.")

        mark_onboarding_complete = getattr(
            self.repository, "mark_onboarding_complete", None
        )
        if mark_onboarding_complete is not None:
            try:
                await mark_onboarding_complete(auth_user_id)
            except Exception:
                # A status-write failure must not turn a valid Auth login into
                # a failed login. The next successful login can repair it.
                logger.exception("Failed to mark admin onboarding complete.")

        session = await self.session_store.create_session(
            auth_user_id=auth_user_id,
            user_account_id=account.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        result = LoginResult(
            session=session,
            user=AuthenticatedUser(
                auth_user_id=auth_user_id,
                user_account_id=account.id,
                username=account.username,
                email=account.email,
                display_name=account.display_name,
                role=account.role,
            ),
        )
        logger.event(
            "auth.login.succeeded",
            fields={"user_account_id": account.id, "role": account.role.value},
        )
        return result
