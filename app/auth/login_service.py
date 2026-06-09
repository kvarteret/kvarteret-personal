from __future__ import annotations

import logging
from dataclasses import dataclass

from app.auth.legacy_passwords import verify_aspnet_identity_hash
from app.auth.models import AuthenticatedUser, WebSession
from app.auth.repository import AuthRepositoryProtocol
from app.auth.roles import highest_role
from app.auth.session_store import SessionStoreProtocol
from app.auth.supabase_auth import SupabaseAuthGatewayProtocol

logger = logging.getLogger(__name__)


class LoginError(Exception):
    """Raised when login fails."""


@dataclass(slots=True)
class LoginResult:
    session: WebSession
    user: AuthenticatedUser
    migrated_from_legacy: bool


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

    async def login_with_bridge(
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
        if account:
            auth_user_id = await self.supabase_auth.sign_in_with_password(
                account.email, password
            )
            if auth_user_id is None:
                logger.warning(
                    "login failed",
                    extra={
                        "event": "auth.login.failed",
                        "event_data": {
                            "identifier": normalized_identifier,
                            "reason": "invalid_credentials",
                        },
                    },
                )
                raise LoginError("Invalid credentials.")
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
                migrated_from_legacy=False,
            )
            logger.info(
                "login succeeded",
                extra={
                    "event": "auth.login.succeeded",
                    "event_data": {
                        "identifier": normalized_identifier,
                        "user_account_id": account.id,
                        "role": account.role.value,
                        "migrated_from_legacy": False,
                    },
                },
            )
            return result
        legacy_user = await self.repository.get_legacy_user_by_identifier(
            normalized_identifier
        )
        if legacy_user is None or not verify_aspnet_identity_hash(
            legacy_user.password_hash, password
        ):
            logger.warning(
                "login failed",
                extra={
                    "event": "auth.login.failed",
                    "event_data": {
                        "identifier": normalized_identifier,
                        "reason": "invalid_credentials",
                    },
                },
            )
            raise LoginError("Invalid credentials.")

        legacy_roles = await self.repository.get_legacy_roles(legacy_user.id)
        role = highest_role(legacy_roles)
        auth_user_id = await self.supabase_auth.create_user_from_legacy(
            legacy_user, password
        )
        account = await self.repository.upsert_user_account(
            auth_user_id=auth_user_id,
            legacy_user=legacy_user,
            role=role,
        )
        group_ids = await self.repository.get_legacy_group_ids(legacy_user.id)
        await self.repository.replace_group_admin_memberships(auth_user_id, group_ids)
        await self.repository.record_migration_event(
            legacy_user_id=legacy_user.id,
            auth_user_id=auth_user_id,
            email=legacy_user.email,
            outcome="migrated",
        )
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
            migrated_from_legacy=True,
        )
        logger.info(
            "login succeeded",
            extra={
                "event": "auth.login.succeeded",
                "event_data": {
                    "identifier": normalized_identifier,
                    "user_account_id": account.id,
                    "role": account.role.value,
                    "migrated_from_legacy": True,
                },
            },
        )
        return result
