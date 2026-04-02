from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser
from app.auth.roles import UserRole
from app.dependencies import get_current_user, require_authenticated_user
from app.web.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME


def make_authenticated_user(role: UserRole = UserRole.ADMIN) -> AuthenticatedUser:
    return AuthenticatedUser(
        auth_user_id=uuid4(),
        user_account_id=5,
        username="admin",
        email="admin.user@example.test",
        display_name="System User",
        role=role,
    )


def override_authenticated_user(app: FastAPI, user: AuthenticatedUser | None) -> None:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_authenticated_user] = lambda: user


def prime_csrf(
    client: TestClient,
    *,
    path: str = "/",
    cookies: dict[str, str] | None = None,
) -> str:
    if cookies:
        client.cookies.update(cookies)
    response = client.get(path)
    assert response.status_code < 400
    return client.cookies[CSRF_COOKIE_NAME]


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER_NAME: client.cookies[CSRF_COOKIE_NAME]}
