from __future__ import annotations

from uuid import UUID

import pytest

from app.auth.dev_auth import DevAuthGateway, dev_auth_user_id
from app.config import Settings, validate_production_secrets


@pytest.mark.asyncio
async def test_dev_auth_accepts_only_configured_credentials() -> None:
    gateway = DevAuthGateway(
        Settings(
            app_env="development",
            dev_admin_email="dev@example.com",
            dev_admin_password="local-secret",
        )
    )

    authenticated_id = await gateway.sign_in_with_password(
        " DEV@example.com ", "local-secret"
    )

    assert authenticated_id == dev_auth_user_id("dev@example.com")
    assert (
        await gateway.sign_in_with_password("dev@example.com", "wrong-password") is None
    )
    assert (
        await gateway.sign_in_with_password("other@example.com", "local-secret") is None
    )


@pytest.mark.asyncio
async def test_dev_auth_account_ids_are_deterministic() -> None:
    gateway = DevAuthGateway(
        Settings(
            app_env="development",
            dev_admin_email="dev@example.com",
            dev_admin_password="local-secret",
        )
    )

    created_id = await gateway.create_user(
        email="new.admin@example.com", password="unused"
    )
    invited_id = await gateway.invite_user(email="new.admin@example.com")

    assert isinstance(created_id, UUID)
    assert created_id == invited_id == dev_auth_user_id("new.admin@example.com")


def test_dev_auth_settings_are_rejected_outside_development() -> None:
    settings = Settings(
        app_env="production",
        app_secret_key="production-secret",
        dev_admin_email="dev@example.com",
        dev_admin_password="local-secret",
    )

    with pytest.raises(ValueError, match="development-only"):
        validate_production_secrets(settings)


def test_dev_auth_gateway_refuses_non_development_environment() -> None:
    with pytest.raises(RuntimeError, match="only available in development"):
        DevAuthGateway(
            Settings(
                app_env="test",
                dev_admin_email="dev@example.com",
                dev_admin_password="local-secret",
            )
        )
