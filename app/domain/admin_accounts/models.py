from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.auth.roles import UserRole


@dataclass(slots=True)
class AdminAccountListItem:
    user_account_id: int
    auth_user_id: UUID
    username: str
    email: str
    display_name: str | None
    role: UserRole
    last_login: datetime | None
    group_admin_group_ids: list[int]
    group_admin_group_count: int
    volunteer_id: int | None = None
    is_legacy_account: bool = False
    associated_groups: list[tuple[int, str, bool]] = field(default_factory=list)
    photo_path: str | None = None
    photo_url: str | None = None


@dataclass(slots=True)
class AdminAccountDetail:
    user_account_id: int
    auth_user_id: UUID
    username: str
    email: str
    display_name: str | None
    role: UserRole
    last_login: datetime | None
    created_at: datetime
    migrated_at: datetime | None
    group_admin_group_ids: list[int]
    onboarding_status: str = "active"
    onboarding_last_sent_at: datetime | None = None
    activated_at: datetime | None = None
    volunteer_id: int | None = None
    is_legacy_account: bool = False
