from __future__ import annotations

from typing import Protocol
from uuid import UUID

from supabase import Client, create_client
from supabase_auth.types import AdminUserAttributes

from app.auth.models import LegacyUser
from app.config import Settings
from app.errors import NotConfiguredError


class SupabaseAuthGatewayProtocol(Protocol):
    async def sign_in_with_password(self, email: str, password: str) -> UUID | None: ...
    async def create_user_from_legacy(self, legacy_user: LegacyUser, password: str) -> UUID: ...
    async def create_user(self, *, email: str, password: str, metadata: dict | None = None) -> UUID: ...
    async def delete_user(self, auth_user_id: UUID) -> None: ...


class SupabaseAuthGateway:
    def __init__(self, settings: Settings) -> None:
        if not settings.supabase_url or not settings.supabase_secret_key:
            raise NotConfiguredError("Supabase credentials are required for authentication.")
        self.client: Client = create_client(settings.supabase_url, settings.supabase_secret_key)

    async def sign_in_with_password(self, email: str, password: str) -> UUID | None:
        try:
            response = self.client.auth.sign_in_with_password({"email": email, "password": password})
        except Exception:
            return None

        user = getattr(response, "user", None)
        if not user or not getattr(user, "id", None):
            return None
        return UUID(str(user.id))

    async def create_user_from_legacy(self, legacy_user: LegacyUser, password: str) -> UUID:
        email = legacy_user.email or f"legacy-{legacy_user.id}@invalid.local"
        return await self.create_user(
            email=email,
            password=password,
            metadata={
                "legacy_user_id": legacy_user.id,
                "legacy_username": legacy_user.username,
            },
        )

    async def create_user(self, *, email: str, password: str, metadata: dict | None = None) -> UUID:
        response = self.client.auth.admin.create_user(
            AdminUserAttributes(
                {
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": metadata or {},
                }
            )
        )
        user = getattr(response, "user", None)
        if not user or not getattr(user, "id", None):
            raise NotConfiguredError("Supabase did not return a user id during auth user creation.")
        return UUID(str(user.id))

    async def delete_user(self, auth_user_id: UUID) -> None:
        self.client.auth.admin.delete_user(str(auth_user_id))
