from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.auth.models import AuthenticatedUser, WebSession


@dataclass(slots=True)
class RequestAuthContext:
    session: WebSession | None
    user: AuthenticatedUser | None


def get_request_auth_context(request: Request) -> RequestAuthContext:
    return RequestAuthContext(
        session=getattr(request.state, "session", None),
        user=getattr(request.state, "current_user", None),
    )


def require_authenticated_user(request: Request) -> AuthenticatedUser:
    user = getattr(request.state, "current_user", None)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return user

