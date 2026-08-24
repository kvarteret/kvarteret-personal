from __future__ import annotations

import hashlib
import hmac
from typing import Protocol

from pydantic import BaseModel, ConfigDict, EmailStr

from app.infrastructure.email.password_reset_templates import (
    PasswordResetEmailTemplateRendererProtocol,
)
from app.infrastructure.email.protocols import EmailSenderProtocol


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr


class PasswordResetServiceProtocol(Protocol):
    async def send_reset_email(self, *, email: str, redirect_to: str) -> bool: ...


class PasswordResetAuthGatewayProtocol(Protocol):
    async def generate_link(
        self,
        *,
        link_type: str,
        email: str,
        redirect_to: str | None = None,
        metadata: dict | None = None,
    ) -> str: ...


class PasswordResetAdminAccountRepositoryProtocol(Protocol):
    async def find_user_account_id_by_email(self, email: str) -> int | None: ...


class PasswordResetService:
    def __init__(
        self,
        *,
        auth_gateway: PasswordResetAuthGatewayProtocol,
        email_sender: EmailSenderProtocol,
        email_renderer: PasswordResetEmailTemplateRendererProtocol,
        admin_account_repository: PasswordResetAdminAccountRepositoryProtocol,
    ) -> None:
        self.auth_gateway = auth_gateway
        self.email_sender = email_sender
        self.email_renderer = email_renderer
        self.admin_account_repository = admin_account_repository

    async def send_reset_email(self, *, email: str, redirect_to: str) -> bool:
        request = PasswordResetRequest(email=email)
        normalized_email = str(request.email).lower()
        # GoTrue identities are shared by multiple surfaces. Only an email
        # linked to a local admin account may receive a Kvarteret reset link.
        # The web route deliberately ignores this return value so unknown and
        # known addresses retain the same public response.
        if (
            await self.admin_account_repository.find_user_account_id_by_email(
                normalized_email
            )
            is None
        ):
            return False
        setup_url = await self.auth_gateway.generate_link(
            link_type="recovery",
            email=normalized_email,
            redirect_to=redirect_to,
        )
        rendered = self.email_renderer.render_password_reset_email(setup_url=setup_url)
        await self.email_sender.send_email(
            recipient_email=normalized_email,
            subject=rendered.subject,
            html_body=rendered.html_body,
        )
        return True


def password_reset_account_key(email: str, secret: str) -> str:
    return _password_reset_key("account", email.strip().lower(), secret)


def password_reset_ip_key(ip_address: str, secret: str) -> str:
    return _password_reset_key("ip", ip_address.strip(), secret)


def _password_reset_key(kind: str, value: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"password-reset:{kind}:{digest}"
