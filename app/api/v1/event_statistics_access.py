"""Who may read arrangement statistics on the website.

The website forwards the browser's Personal session cookie (shared on
``.samfunnetibergen.no`` through ``SESSION_COOKIE_DOMAIN``) server-to-server.
Admin sees every arrangement; Gruppeadmin sees the groups in its group-admin
assignment.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.auth.roles import UserRole
from app.dependencies import get_admin_accounts_service, get_current_user

router = APIRouter()


class StatisticsGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str


class EventStatisticsAccessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    role: UserRole
    groups: list[StatisticsGroup] | None


@router.get(
    "",
    response_model=EventStatisticsAccessResponse,
    operation_id="getEventStatisticsAccess",
    responses={401: {"description": "No Personal session."}, 403: {"description": "Not Admin or Gruppeadmin."}},
)
async def get_event_statistics_access(
    current_user=Depends(get_current_user),
    admin_accounts_service=Depends(get_admin_accounts_service),
) -> JSONResponse:
    if current_user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")
    if current_user.role not in {UserRole.ADMIN, UserRole.GROUP_ADMIN}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access is required.")
    groups = None
    if current_user.role == UserRole.GROUP_ADMIN:
        groups = [
            StatisticsGroup(slug=row["slug"], name=row["name"])
            for row in await admin_accounts_service.group_admin_groups(
                current_user.auth_user_id
            )
        ]
    body = EventStatisticsAccessResponse(
        name=current_user.display_name or current_user.username,
        role=current_user.role,
        groups=groups,
    )
    return JSONResponse(
        content=body.model_dump(mode="json"),
        headers={"Cache-Control": "private, no-store", "Vary": "Cookie"},
    )
