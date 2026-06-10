"""In-application authorization layer.

Defines every guarded capability as a ``Permission`` enum, roles as
named permission bundles, and a ``require_permission`` FastAPI
dependency that replaces ad-hoc role checks in routes.

Design (see ``docs/adr/002-auth-consolidation.md``):
- Permissions are fine-grained capabilities (e.g. ``VOLUNTEER_READ``).
- Roles are bundles of permissions stored in code, not the database.
- A ``role_grants`` table maps user accounts to roles, optionally
  scoped to a specific group (``group_id``).
- ``require_permission`` checks the current user's grants and raises
  HTTP 403 if the required permission is absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from fastapi import Depends, HTTPException, Request, status

from app.auth.models import AuthenticatedUser
from app.auth.roles import UserRole


# ── Permissions ───────────────────────────────────────────────────


class Permission(StrEnum):
    # Volunteer management
    VOLUNTEER_READ = "volunteer.read"
    VOLUNTEER_WRITE = "volunteer.write"
    VOLUNTEER_DELETE = "volunteer.delete"

    # Application management
    APPLICATION_READ = "application.read"
    APPLICATION_APPROVE = "application.approve"
    APPLICATION_REJECT = "application.reject"
    APPLICATION_INVITE = "application.invite"
    APPLICATION_DELETE = "application.delete"

    # Group management
    GROUP_READ = "group.read"
    GROUP_WRITE = "group.write"
    GROUP_DELETE = "group.delete"

    # Course management
    COURSE_READ = "course.read"
    COURSE_WRITE = "course.write"
    COURSE_DELETE = "course.delete"

    # Admin account management
    ACCOUNT_READ = "account.read"
    ACCOUNT_WRITE = "account.write"
    ACCOUNT_DELETE = "account.delete"

    # Spotify
    SPOTIFY_CONTROL = "spotify.control"

    # Stats and feedback
    STATS_READ = "stats.read"
    FEEDBACK_MANAGE = "feedback.manage"


# ── Role bundles ──────────────────────────────────────────────────

# Each role is a frozen set of permissions.  These are defined in code,
# not the database, so adding a permission to a role is a code change
# that goes through review.

ROLES: dict[UserRole, frozenset[Permission]] = {
    UserRole.ADMIN: frozenset(Permission),
    UserRole.GROUP_ADMIN: frozenset(
        [
            Permission.VOLUNTEER_READ,
            Permission.APPLICATION_READ,
            Permission.APPLICATION_APPROVE,
            Permission.APPLICATION_REJECT,
            Permission.APPLICATION_INVITE,
            Permission.APPLICATION_DELETE,
            Permission.GROUP_READ,
            Permission.COURSE_READ,
        ]
    ),
}


# ── Grant model ───────────────────────────────────────────────────


@dataclass(slots=True)
class RoleGrant:
    user_account_id: int
    role: UserRole
    group_id: int | None  # None = global; non-None = scoped to one group
    granted_by: int
    granted_at: str | None = None


class GrantRepositoryProtocol(Protocol):
    async def get_grants_for_user(
        self, user_account_id: int, *, group_id: int | None = None
    ) -> list[RoleGrant]: ...


# ── Dependency ────────────────────────────────────────────────────


def _get_current_user(request: Request) -> AuthenticatedUser | None:
    return getattr(request.state, "current_user", None)


def require_permission(
    permission: Permission,
    *,
    group_scoped: bool = False,
):
    """FastAPI dependency factory.

    Usage in a route::

        @router.get("/volunteers")
        async def list_volunteers(
            _: None = Depends(require_permission(Permission.VOLUNTEER_READ)),
        ):
            ...
    """

    async def check(
        current_user: AuthenticatedUser | None = Depends(_get_current_user),
    ) -> None:
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
            )

        user_role = current_user.role
        allowed = ROLES.get(user_role, frozenset())

        if permission not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission.value}' is required.",
            )

    return check
