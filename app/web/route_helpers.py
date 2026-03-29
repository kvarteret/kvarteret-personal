from __future__ import annotations

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.observability import log_admin_activity


def not_configured_http_exception(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
    )


def blocked_http_exception(blockers: list[str]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=" ".join(blockers),
    )


def redirect_to(path: str) -> RedirectResponse:
    return RedirectResponse(url=path, status_code=status.HTTP_303_SEE_OTHER)


def log_and_redirect(
    *,
    request: Request,
    user,
    action: str,
    subject_type: str,
    redirect_path: str,
    subject_id: int | None = None,
    details: dict | None = None,
) -> RedirectResponse:
    log_admin_activity(
        request=request,
        user=user,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        details=details,
    )
    return redirect_to(redirect_path)
