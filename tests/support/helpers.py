from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI

from app.auth.models import AuthenticatedUser
from app.auth.roles import UserRole
from app.dependencies import get_current_user, require_authenticated_user


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
