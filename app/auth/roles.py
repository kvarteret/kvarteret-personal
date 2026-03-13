from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "Admin"
    GROUP_ADMIN = "Gruppeadmin"
    VOLUNTEER = "Frivillig"
    VIEWER = "Tilskuer"


ROLE_PRIORITY = {
    UserRole.ADMIN: 3,
    UserRole.GROUP_ADMIN: 2,
    UserRole.VOLUNTEER: 1,
    UserRole.VIEWER: 0,
}


def highest_role(role_names: list[str]) -> UserRole:
    if not role_names:
        return UserRole.VIEWER

    roles = []
    for role_name in role_names:
        try:
            roles.append(UserRole(role_name))
        except ValueError:
            continue

    if not roles:
        return UserRole.VIEWER

    return max(roles, key=lambda role: ROLE_PRIORITY[role])

