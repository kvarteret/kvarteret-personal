from __future__ import annotations

import hashlib
import hmac
from typing import Protocol

from pydantic import BaseModel, ConfigDict, EmailStr


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr


class PasswordResetServiceProtocol(Protocol):
    async def send_reset_email(self, *, email: str, redirect_to: str) -> bool: ...


class PasswordResetAuthGatewayProtocol(Protocol):
    async def send_password_reset_email(
        self, *, email: str, redirect_to: str | None = None
    ) -> None: ...


class PasswordResetService:
    def __init__(
        self,
        *,
        auth_gateway: PasswordResetAuthGatewayProtocol,
    ) -> None:
        self.auth_gateway = auth_gateway

    async def send_reset_email(self, *, email: str, redirect_to: str) -> bool:
        request = PasswordResetRequest(email=email)
        normalized_email = str(request.email).lower()
        await self.auth_gateway.send_password_reset_email(
            email=normalized_email,
            redirect_to=redirect_to,
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
