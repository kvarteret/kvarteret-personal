from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthenticatedUser

router = APIRouter()


class AuthenticatedUserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    auth_user_id: str
    user_account_id: int | None
    username: str
    email: str
    display_name: str | None
    role: str


@router.get("/auth/me", response_model=AuthenticatedUserResponse)
async def get_current_authenticated_user(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    return AuthenticatedUserResponse(
        auth_user_id=str(current_user.auth_user_id),
        user_account_id=current_user.user_account_id,
        username=current_user.username,
        email=current_user.email,
        display_name=current_user.display_name,
        role=current_user.role.name.lower(),
    )
