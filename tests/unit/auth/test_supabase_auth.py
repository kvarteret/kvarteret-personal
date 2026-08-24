from __future__ import annotations

import json

import httpx
import pytest

from app.auth.supabase_auth import RecoveryTokenError, SupabaseAuthGateway
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
async def test_find_user_id_by_email_walks_admin_user_pages() -> None:
    requests: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(dict(request.url.params))
        page = request.url.params.get("page")
        if page == "1":
            users = [
                {
                    "id": "f2f6f0ac-6f0c-4e4f-b3a2-9bc0713b5d5a",
                    "email": f"other-{index}@example.com",
                }
                for index in range(1000)
            ]
        elif page == "2":
            users = [
                {"id": "7cc2c6a2-2a22-44ba-995e-f8eb8a9d4b6b", "email": "ADMIN@example.com"}
            ]
        else:
            users = []
        return httpx.Response(200, json={"users": users})

    gateway = SupabaseAuthGateway(
        Settings(
            supabase_url="https://project.supabase.co",
            supabase_secret_key="service-role-key",
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    try:
        auth_user_id = await gateway.find_user_id_by_email(" admin@example.com ")
    finally:
        await gateway.aclose()

    assert str(auth_user_id) == "7cc2c6a2-2a22-44ba-995e-f8eb8a9d4b6b"
    assert requests == [
        {"page": "1", "per_page": "1000"},
        {"page": "2", "per_page": "1000"},
    ]


@pytest.mark.asyncio
async def test_update_password_verifies_hash_before_using_recovery_session() -> None:
    requests: list[tuple[str, str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else {}
        requests.append((request.method, request.url.path, payload))
        if request.url.path.endswith("/verify"):
            return httpx.Response(200, json={"access_token": "recovery-access-token"})
        assert request.headers["authorization"] == "Bearer recovery-access-token"
        return httpx.Response(
            200,
            json={"id": "7cc2c6a2-2a22-44ba-995e-f8eb8a9d4b6b"},
        )

    gateway = SupabaseAuthGateway(
        Settings(
            supabase_url="https://project.supabase.co",
            supabase_secret_key="service-role-key",
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    try:
        auth_user_id = await gateway.update_password_with_token_hash(
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
    assert str(auth_user_id) == "7cc2c6a2-2a22-44ba-995e-f8eb8a9d4b6b"


@pytest.mark.asyncio
async def test_expired_recovery_token_has_a_distinct_domain_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"msg": "Token has expired"})

    gateway = SupabaseAuthGateway(
        Settings(
            supabase_url="https://project.supabase.co",
            supabase_secret_key="service-role-key",
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    try:
        with pytest.raises(RecoveryTokenError):
            await gateway.update_password_with_token_hash(
                "expired-token", "recovery", "UpdatedPassword123"
            )
    finally:
        await gateway.aclose()
