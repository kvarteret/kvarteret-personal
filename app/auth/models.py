from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.auth.roles import UserRole


@dataclass(slots=True)
class LegacyUser:
    id: int
    username: str
    email: str | None
    display_name: str | None
    password_hash: str


@dataclass(slots=True)
class UserAccount:
    id: int
    auth_user_id: UUID
    legacy_user_id: int | None
    username: str
    email: str
    display_name: str | None
    role: UserRole
    last_login: datetime | None


@dataclass(slots=True)
class AuthenticatedUser:
    auth_user_id: UUID
    user_account_id: int | None
    username: str
    email: str
    display_name: str | None
    role: UserRole


@dataclass(slots=True)
class WebSession:
    session_id: str
    auth_user_id: UUID
    user_account_id: int | None
    expires_at: datetime

