from __future__ import annotations

import json

import httpx
import pytest

from app.auth.supabase_auth import SupabaseAuthGateway
from app.config import Settings


@pytest.mark.asyncio
async def test_generate_link_returns_scanner_safe_password_setup_link() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/v1/admin/generate_link"
        return httpx.Response(
            200,
            json={
                "action_link": "https://project.supabase.co/auth/v1/verify?token=secret",
                "hashed_token": "hashed-token",
                "verification_type": "recovery",
            },
        )

    gateway = SupabaseAuthGateway(
        Settings(
            supabase_url="https://project.supabase.co",
            supabase_secret_key="service-role-key",
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    try:
        link = await gateway.generate_link(
            link_type="recovery",
            email="admin@example.com",
            redirect_to="https://personal.example.com/set-password",
        )
    finally:
        await gateway.aclose()

    assert link == (
        "https://personal.example.com/set-password"
        "#token_hash=hashed-token&type=recovery"
    )


@pytest.mark.asyncio
async def test_update_password_verifies_hash_before_using_recovery_session() -> None:
    requests: list[tuple[str, str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append((request.method, request.url.path, payload))
        if request.url.path.endswith("/verify"):
            return httpx.Response(200, json={"access_token": "recovery-access-token"})
        assert request.headers["authorization"] == "Bearer recovery-access-token"
        return httpx.Response(200, json={})

    gateway = SupabaseAuthGateway(
        Settings(
            supabase_url="https://project.supabase.co",
            supabase_secret_key="service-role-key",
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    try:
        await gateway.update_password_with_token_hash(
            "hashed-token", "recovery", "UpdatedPassword123"
        )
    finally:
        await gateway.aclose()

    assert requests == [
        (
            "POST",
            "/auth/v1/verify",
            {"token_hash": "hashed-token", "type": "recovery"},
        ),
        ("PUT", "/auth/v1/user", {"password": "UpdatedPassword123"}),
    ]
