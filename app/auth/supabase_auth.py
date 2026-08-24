from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import UUID

import httpx

from app.config import Settings
from app.errors import NotConfiguredError

_API_VERSION_HEADER = "X-Supabase-Api-Version"
_API_VERSION = "2024-01-01"


class SupabaseAuthGatewayProtocol(Protocol):
    async def sign_in_with_password(self, email: str, password: str) -> UUID | None: ...
    async def find_user_id_by_email(self, email: str) -> UUID | None: ...
    async def create_user(
        self, *, email: str, password: str, metadata: dict | None = None
    ) -> UUID: ...
    async def invite_user(
        self,
        *,
        email: str,
        metadata: dict | None = None,
        redirect_to: str | None = None,
    ) -> UUID: ...
    async def generate_link(
        self,
        *,
        link_type: str,
        email: str,
        redirect_to: str | None = None,
        metadata: dict | None = None,
    ) -> str: ...
    async def update_user_password(self, auth_user_id: UUID, password: str) -> None: ...
    async def update_password_with_access_token(
        self, access_token: str, password: str
    ) -> UUID | None: ...
    async def update_password_with_token_hash(
        self, token_hash: str, verification_type: str, password: str
    ) -> UUID | None: ...
    async def delete_user(self, auth_user_id: UUID) -> None: ...
    async def aclose(self) -> None: ...


class SupabaseAuthGateway:
    def __init__(
        self, settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        if not settings.supabase_url or not settings.supabase_secret_key:
            raise NotConfiguredError(
                "Supabase credentials are required for authentication."
            )
        self._base_url = f"{settings.supabase_url.rstrip('/')}/auth/v1"
        self._headers = {
            "apikey": settings.supabase_secret_key,
            "Authorization": f"Bearer {settings.supabase_secret_key}",
            _API_VERSION_HEADER: _API_VERSION,
        }
        self._client = client or httpx.AsyncClient(timeout=20.0, follow_redirects=True)

    async def sign_in_with_password(self, email: str, password: str) -> UUID | None:
        try:
            response = await self._request(
                "POST",
                "token",
                params={"grant_type": "password"},
                json={
                    "email": email,
                    "password": password,
                    "data": {},
                    "gotrue_meta_security": {"captcha_token": None},
                },
            )
        except httpx.HTTPError:
            return None
        return _extract_user_id(response.json())

    async def find_user_id_by_email(self, email: str) -> UUID | None:
        """Find an existing Auth identity without creating or modifying it.

        GoTrue exposes list-users rather than a service-role email lookup. Walk
        the documented pages so an existing identity cannot be missed once a
        project has more users than the page size.
        """
        normalized_email = email.strip().lower()
        page = 1
        per_page = 1000
        while True:
            response = await self._request(
                "GET",
                "admin/users",
                params={"page": page, "per_page": per_page},
            )
            payload = response.json()
            users = payload.get("users", []) if isinstance(payload, dict) else []
            if not isinstance(users, list):
                raise NotConfiguredError(
                    "Supabase returned an invalid user list during auth reconciliation."
                )
            for user in users:
                if not isinstance(user, dict):
                    continue
                candidate_email = user.get("email")
                if (
                    isinstance(candidate_email, str)
                    and candidate_email.strip().lower() == normalized_email
                    and user.get("id")
                ):
                    return UUID(str(user["id"]))
            # Some GoTrue versions cap ``per_page`` below the requested value.
            # Continue until an empty page so a capped response cannot hide a
            # matching identity on a later page.
            if not users:
                return None
            page += 1

    async def create_user(
        self, *, email: str, password: str, metadata: dict | None = None
    ) -> UUID:
        response = await self._request(
            "POST",
            "admin/users",
            json={
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": metadata or {},
            },
        )
        auth_user_id = _extract_user_id(response.json())
        if auth_user_id is None:
            raise NotConfiguredError(
                "Supabase did not return a user id during auth user creation."
            )
        return auth_user_id

    async def invite_user(
        self,
        *,
        email: str,
        metadata: dict | None = None,
        redirect_to: str | None = None,
    ) -> UUID:
        params = {"redirect_to": redirect_to} if redirect_to else None
        response = await self._request(
            "POST",
            "invite",
            params=params,
            json={
                "email": email,
                "data": metadata or {},
            },
        )
        auth_user_id = _extract_user_id(response.json())
        if auth_user_id is None:
            raise NotConfiguredError(
                "Supabase did not return a user id during auth invite."
            )
        return auth_user_id

    async def generate_link(
        self,
        *,
        link_type: str,
        email: str,
        redirect_to: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "type": link_type,
            "email": email,
        }
        if redirect_to:
            payload["redirect_to"] = redirect_to
        if metadata:
            payload["data"] = metadata
        response = await self._request("POST", "admin/generate_link", json=payload)
        response_payload = response.json()
        action_link = response_payload.get("action_link")
        if not isinstance(action_link, str) or not action_link:
            raise NotConfiguredError("Supabase did not return an email action link.")
        hashed_token = response_payload.get("hashed_token")
        verification_type = response_payload.get("verification_type")
        if redirect_to and isinstance(hashed_token, str) and hashed_token:
            if isinstance(verification_type, str) and verification_type:
                return _password_setup_link(
                    redirect_to,
                    token_hash=hashed_token,
                    verification_type=verification_type,
                )
        return action_link

    async def update_user_password(self, auth_user_id: UUID, password: str) -> None:
        await self._request(
            "PUT",
            f"admin/users/{auth_user_id}",
            json={"password": password},
        )

    async def update_password_with_access_token(
        self, access_token: str, password: str
    ) -> UUID | None:
        response = await self._request(
            "PUT",
            "user",
            json={"password": password},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return _extract_user_id(response.json())

    async def update_password_with_token_hash(
        self, token_hash: str, verification_type: str, password: str
    ) -> UUID | None:
        if verification_type != "recovery":
            raise ValueError("Unsupported password setup verification type.")
        response = await self._request(
            "POST",
            "verify",
            json={"token_hash": token_hash, "type": verification_type},
        )
        access_token = response.json().get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise NotConfiguredError("Supabase did not return a recovery session.")
        return await self.update_password_with_access_token(access_token, password)

    async def delete_user(self, auth_user_id: UUID) -> None:
        await self._request(
            "DELETE",
            f"admin/users/{auth_user_id}",
            json={"should_soft_delete": False},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        response = await self._client.request(
            method,
            f"{self._base_url}/{path.lstrip('/')}",
            headers={**self._headers, **(headers or {})},
            params=params,
            json=json,
        )
        response.raise_for_status()
        return response


def _extract_user_id(payload: dict[str, Any]) -> UUID | None:
    user = payload.get("user")
    if isinstance(user, dict) and user.get("id"):
        return UUID(str(user["id"]))
    if payload.get("id"):
        return UUID(str(payload["id"]))
    return None


def _password_setup_link(
    redirect_to: str, *, token_hash: str, verification_type: str
) -> str:
    parts = urlsplit(redirect_to)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            parts.query,
            urlencode({"token_hash": token_hash, "type": verification_type}),
        )
    )
