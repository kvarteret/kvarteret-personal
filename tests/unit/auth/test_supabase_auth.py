from __future__ import annotations

import json

import httpx
import pytest

from app.auth.supabase_auth import SupabaseAuthGateway
from app.config import Settings


@pytest.mark.asyncio
async def test_supabase_gateway_sends_native_password_recovery_email() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        captured["apikey"] = request.headers.get("apikey")
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = SupabaseAuthGateway(
        Settings(
            supabase_url="https://project.supabase.co",
            supabase_secret_key="service-role-key",
        ),
        client=client,
    )

    try:
        await gateway.send_password_reset_email(
            email="admin@example.com",
            redirect_to="https://personal.example.com/set-password",
        )
    finally:
        await gateway.aclose()

    assert captured == {
        "method": "POST",
        "url": (
            "https://project.supabase.co/auth/v1/recover?"
            "redirect_to=https%3A%2F%2Fpersonal.example.com%2Fset-password"
        ),
        "payload": {
            "email": "admin@example.com",
            "gotrue_meta_security": {"captcha_token": None},
        },
        "apikey": "service-role-key",
    }
