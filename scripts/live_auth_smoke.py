from __future__ import annotations

import asyncio
import secrets
import string

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.auth.repository import get_auth_repository
from app.auth.roles import UserRole
from app.auth.supabase_auth import get_supabase_auth_gateway
from app.db.session import get_session_factory
from app.db.tables import (
    auth_identities,
    auth_refresh_tokens,
    auth_sessions,
    auth_users,
    user_accounts,
    web_sessions,
)
from app.main import create_app


def _random_string(length: int = 12) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def main() -> None:
    email = f"codex-smoke-{_random_string()}@example.test"
    password = f"Pw-{_random_string(18)}!"
    username = f"codex_{_random_string(8)}"

    gateway = get_supabase_auth_gateway()
    repository = get_auth_repository()
    auth_user_id = await gateway.create_user(
        email=email,
        password=password,
        metadata={"smoke_test": True, "username": username},
    )

    try:
        account = await repository.create_direct_user_account(
            auth_user_id=auth_user_id,
            username=username,
            email=email,
            display_name="Smoke User",
            role=UserRole.ADMIN,
        )

        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            login_response = await client.post(
                "/login",
                data={"identifier": email, "password": password},
                follow_redirects=False,
            )
            if login_response.status_code != 303:
                raise RuntimeError(
                    f"Expected 303 from /login, got {login_response.status_code}: {login_response.text}"
                )

            auth_response = await client.get("/api/v1/auth/me")
            if auth_response.status_code != 200:
                raise RuntimeError(
                    f"Expected 200 from /api/v1/auth/me, got {auth_response.status_code}: {auth_response.text}"
                )

            payload = auth_response.json()
            print("LOGIN_OK", payload["email"], payload["role"], account.id)
    finally:
        async with get_session_factory()() as session:
            await session.execute(delete(web_sessions).where(web_sessions.c.auth_user_id == auth_user_id))
            await session.execute(delete(user_accounts).where(user_accounts.c.auth_user_id == auth_user_id))
            await session.execute(delete(auth_refresh_tokens).where(auth_refresh_tokens.c.user_id == str(auth_user_id)))
            await session.execute(delete(auth_sessions).where(auth_sessions.c.user_id == auth_user_id))
            await session.execute(delete(auth_identities).where(auth_identities.c.user_id == auth_user_id))
            await session.execute(delete(auth_users).where(auth_users.c.id == auth_user_id))
            await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
