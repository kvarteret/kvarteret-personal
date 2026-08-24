from __future__ import annotations

import pytest

from app.auth.password_reset_service import (
    PasswordResetService,
    password_reset_account_key,
    password_reset_ip_key,
)
from app.infrastructure.email.password_reset_templates import (
    PasswordResetEmail,
    PasswordResetEmailTemplateRenderer,
)


class FakeAuthGateway:
    def __init__(self) -> None:
        self.reset_requests: list[dict[str, str | None]] = []

    async def generate_link(
        self,
        *,
        link_type: str,
        email: str,
        redirect_to: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        self.reset_requests.append(
            {
                "link_type": link_type,
                "email": email,
                "redirect_to": redirect_to,
            }
        )
        return "https://personal.example.com/set-password#token_hash=hashed-token&type=recovery"


class FakeAdminAccountRepository:
    def __init__(self, user_account_id: int | None = 1) -> None:
        self.user_account_id = user_account_id
        self.lookups: list[str] = []

    async def find_user_account_id_by_email(self, email: str) -> int | None:
        self.lookups.append(email)
        return self.user_account_id


class FakeEmailRenderer:
    def render_password_reset_email(self, *, setup_url: str) -> PasswordResetEmail:
        return PasswordResetEmail(
            subject="Reset password",
            html_body=f"Reset: {setup_url}",
        )


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send_email(
        self, *, recipient_email: str, subject: str, html_body: str
    ) -> None:
        self.sent.append(
            {
                "recipient_email": recipient_email,
                "subject": subject,
                "html_body": html_body,
            }
        )


@pytest.mark.asyncio
async def test_password_reset_uses_application_email_sender() -> None:
    auth_gateway = FakeAuthGateway()
    email_sender = FakeEmailSender()
    admin_account_repository = FakeAdminAccountRepository()
    service = PasswordResetService(
        auth_gateway=auth_gateway,
        email_sender=email_sender,
        email_renderer=FakeEmailRenderer(),
        admin_account_repository=admin_account_repository,
    )

    delivered = await service.send_reset_email(
        email=" ADMIN@example.com ",
        redirect_to="https://personal.example.com/set-password",
    )

    assert delivered is True
    assert auth_gateway.reset_requests == [
        {
            "link_type": "recovery",
            "email": "admin@example.com",
            "redirect_to": "https://personal.example.com/set-password",
        }
    ]
    assert email_sender.sent == [
        {
            "recipient_email": "admin@example.com",
            "subject": "Reset password",
            "html_body": (
                "Reset: https://personal.example.com/set-password"
                "#token_hash=hashed-token&type=recovery"
            ),
        }
    ]


@pytest.mark.asyncio
async def test_password_reset_does_not_generate_link_for_non_admin_auth_user() -> None:
    auth_gateway = FakeAuthGateway()
    admin_account_repository = FakeAdminAccountRepository(user_account_id=None)
    service = PasswordResetService(
        auth_gateway=auth_gateway,
        email_sender=FakeEmailSender(),
        email_renderer=FakeEmailRenderer(),
        admin_account_repository=admin_account_repository,
    )

    delivered = await service.send_reset_email(
        email="volunteer@example.com",
        redirect_to="https://personal.example.com/set-password",
    )

    assert delivered is False
    assert auth_gateway.reset_requests == []
    assert admin_account_repository.lookups == ["volunteer@example.com"]


def test_password_reset_email_template_contains_setup_link() -> None:
    rendered = PasswordResetEmailTemplateRenderer().render_password_reset_email(
        setup_url=(
            "https://personal.example.com/set-password"
            "#token_hash=hashed-token&type=recovery"
        )
    )

    assert rendered.subject == "Tilbakestill passordet ditt hos Kvarteret"
    assert "Velg nytt passord" in rendered.html_body
    assert "#token_hash=hashed-token&amp;type=recovery" in rendered.html_body


def test_password_reset_rate_limit_keys_do_not_contain_sensitive_values() -> None:
    account_key = password_reset_account_key("Admin@Example.com", "secret")
    ip_key = password_reset_ip_key("192.0.2.10", "secret")

    assert "admin@example.com" not in account_key
    assert "192.0.2.10" not in ip_key
    assert account_key == password_reset_account_key(" admin@example.com ", "secret")
    assert account_key.startswith("password-reset:account:")
    assert ip_key.startswith("password-reset:ip:")
