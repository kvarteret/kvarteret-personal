from __future__ import annotations

from app.auth.dev_auth import DevAuthGateway
from app.auth.supabase_auth import SupabaseAuthGateway
from app.config import Settings
from app.infrastructure.email.console import ConsoleEmailSender
from app.infrastructure.email.smtp import SmtpEmailSender
from app.infrastructure.storage.local_dir import LocalDirectoryStorage
from app.infrastructure.storage.service import StorageService
from app.runtime import (
    _build_email_sender,
    _build_storage_service,
    _build_supabase_auth_gateway,
)


def test_development_uses_local_adapters_without_external_credentials() -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        dev_admin_email="dev@example.com",
        dev_admin_password="local-secret",
    )

    assert isinstance(_build_storage_service(settings), LocalDirectoryStorage)
    assert isinstance(_build_email_sender(settings), ConsoleEmailSender)
    assert isinstance(_build_supabase_auth_gateway(settings), DevAuthGateway)


def test_configured_external_adapters_take_precedence() -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        azure_blob_connection_string=(
            "DefaultEndpointsProtocol=https;"
            "AccountName=devstore;"
            "AccountKey=ZmFrZQ==;"
            "EndpointSuffix=core.windows.net"
        ),
        SMTP_SERVER="smtp.example.com",
        supabase_url="https://example.supabase.co",
        supabase_secret_key="service-key",
    )

    assert isinstance(_build_storage_service(settings), StorageService)
    assert isinstance(_build_email_sender(settings), SmtpEmailSender)
    assert isinstance(_build_supabase_auth_gateway(settings), SupabaseAuthGateway)
