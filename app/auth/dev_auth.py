"""Development-only auth gateway.

Lets the admin UI work against the local harness database without any
Supabase project. Selected by ``app/runtime.py`` only when
``APP_ENV=development``, Supabase is not configured, and explicit
``DEV_ADMIN_EMAIL``/``DEV_ADMIN_PASSWORD`` values are set;
``validate_production_secrets`` refuses those settings in production.

Auth-user ids are deterministic (UUIDv5 of the email), so seed scripts
can create ``user_accounts`` rows whose ``auth_user_id`` matches what a
login will produce.
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid5

from app.config import Settings

logger = logging.getLogger(__name__)

_DEV_AUTH_NAMESPACE = UUID("8b1dcc10-5b1f-4d8e-9d27-1d2f9c0a7e55")


def dev_auth_user_id(email: str) -> UUID:
    """Deterministic auth-user id for a dev account email."""
    return uuid5(_DEV_AUTH_NAMESPACE, email.strip().lower())


class DevAuthGateway:
    """Implements ``SupabaseAuthGatewayProtocol`` for local development."""

    def __init__(self, settings: Settings) -> None:
        if settings.app_env != "development":
            raise RuntimeError("DevAuthGateway is only available in development.")
        self._email = (settings.dev_admin_email or "").strip().lower()
        self._password = settings.dev_admin_password or ""
        if not self._email or not self._password:
            raise RuntimeError(
                "DEV_ADMIN_EMAIL and DEV_ADMIN_PASSWORD are required for "
                "the development auth gateway."
            )
        logger.warning(
            "Development auth gateway active — admin login accepts only %s",
            self._email,
        )

    async def sign_in_with_password(self, email: str, password: str) -> UUID | None:
        if email.strip().lower() == self._email and password == self._password:
            return dev_auth_user_id(email)
        return None

    # Account-management operations succeed with deterministic ids so the
    # admin-accounts UI remains usable against the local database.
    async def create_user(
        self, *, email: str, password: str, metadata: dict | None = None
    ) -> UUID:
        return dev_auth_user_id(email)

    async def invite_user(
        self,
        *,
        email: str,
        metadata: dict | None = None,
        redirect_to: str | None = None,
    ) -> UUID:
        return dev_auth_user_id(email)

    async def generate_link(
        self,
        *,
        link_type: str,
        email: str,
        redirect_to: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        return f"http://localhost:8000/dev/auth-link?type={link_type}&email={email}"

    async def send_password_reset_email(
        self, *, email: str, redirect_to: str | None = None
    ) -> None:
        logger.info(
            "Development password reset requested.",
            extra={
                "event": "auth.password_reset.requested",
                "event_data": {"status": "accepted"},
            },
        )

    async def update_user_password(self, auth_user_id: UUID, password: str) -> None:
        return None

    async def update_password_with_access_token(
        self, access_token: str, password: str
    ) -> None:
        return None

    async def delete_user(self, auth_user_id: UUID) -> None:
        return None

    async def aclose(self) -> None:
        return None
