from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import (
    get_rate_limiter,
    require_authenticated_user,
)
from app.db.rate_limit import RateLimitExceeded, RateLimiter
from app.observability import emit_event

router = APIRouter()

logger = logging.getLogger("app.web.client_errors")

# Generous ceiling: this endpoint exists so frontend failures become visible
# in PostHog logs, but a single page session can legitimately produce several
# reports, so the window is broad and only stops runaway loops.
_ERROR_REPORT_LIMIT = 60
_ERROR_REPORT_WINDOW_SECONDS = 60


class ClientErrorReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_type: str = Field(default="Error", max_length=120)
    error_text: str = Field(default="", max_length=1200)
    error_source: str = Field(default="", max_length=300)


@router.post("/")
async def report_client_error(
    request: Request,
    body: ClientErrorReport,
    current_user=Depends(require_authenticated_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
):
    rate_limit_key = f"client-error:{current_user.user_account_id or 'unknown'}"
    try:
        await rate_limiter.hit(
            rate_limit_key,
            limit=_ERROR_REPORT_LIMIT,
            window_seconds=_ERROR_REPORT_WINDOW_SECONDS,
        )
    except RateLimitExceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many client error reports.",
        ) from None

    # Structured fields go through the observability sanitizer (redacts
    # emails, query strings, bearer tokens) before export to PostHog logs.
    emit_event(
        logger,
        "web.client_error",
        level=logging.WARNING,
        fields={
            "error_type": body.error_type[:120] or "Error",
            "error_text": body.error_text[:1000],
            "error_source": body.error_source[:250],
            "route_template": request.url.path,
        },
    )
    return {"ok": True}
