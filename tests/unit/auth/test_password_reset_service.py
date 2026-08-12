from __future__ import annotations

import pytest

from app.auth.password_reset_service import (
    PasswordResetService,
    password_reset_account_key,
    password_reset_ip_key,
)


class FakeAuthGateway:
    def __init__(self) -> None:
        self.reset_requests: list[dict[str, str | None]] = []

    async def send_password_reset_email(
        self, *, email: str, redirect_to: str | None = None
    ) -> None:
        self.reset_requests.append({"email": email, "redirect_to": redirect_to})


@pytest.mark.asyncio
async def test_password_reset_uses_supabase_native_recovery_email() -> None:
    auth_gateway = FakeAuthGateway()
    service = PasswordResetService(auth_gateway=auth_gateway)

    delivered = await service.send_reset_email(
        email=" ADMIN@example.com ",
        redirect_to="https://personal.example.com/set-password",
    )

    assert delivered is True
    assert auth_gateway.reset_requests == [
        {
            "email": "admin@example.com",
            "redirect_to": "https://personal.example.com/set-password",
        }
    ]


def test_password_reset_rate_limit_keys_do_not_contain_sensitive_values() -> None:
    account_key = password_reset_account_key("Admin@Example.com", "secret")
    ip_key = password_reset_ip_key("192.0.2.10", "secret")

    assert "admin@example.com" not in account_key
    assert "192.0.2.10" not in ip_key
    assert account_key == password_reset_account_key(" admin@example.com ", "secret")
    assert account_key.startswith("password-reset:account:")
    assert ip_key.startswith("password-reset:ip:")
