from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.dependencies import get_feedback_service
from app.domain.feedback.service import (
    FeedbackDeliveryError,
    FeedbackRateLimitedError,
    FeedbackService,
    FeedbackValidationError,
)
from app.observability import client_ip_from_request

router = APIRouter()


_ALLOWED_SOURCES = {"internbevis-rn", "nettside"}
_ALLOWED_TYPES = {"bug", "feature", "improvement"}


class FeedbackRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    page: str = Field(default="unknown", max_length=200)
    platform: str = Field(default="unknown", max_length=20)
    contact_allowed: bool = Field(default=False)
    contact_email: str | None = Field(default=None, max_length=254)
    user_id: int | None = Field(default=None)
    user_full_name: str | None = Field(default=None, max_length=200)
    source: str = Field(default="internbevis-rn", max_length=50)
    feedback_type: str | None = Field(default=None, max_length=20)


@router.post("/")
async def submit_feedback(
    request: Request,
    body: FeedbackRequest,
    feedback_service: FeedbackService = Depends(get_feedback_service),
):
    source = body.source if body.source in _ALLOWED_SOURCES else "internbevis-rn"
    feedback_type = body.feedback_type if body.feedback_type in _ALLOWED_TYPES else None

    try:
        await feedback_service.submit_feedback(
            name=body.user_full_name,
            email=body.contact_email if body.contact_allowed else None,
            message=body.message,
            page=body.page,
            platform=body.platform,
            user_id=body.user_id,
            source=source,
            feedback_type=feedback_type,
            source_key=client_ip_from_request(request),
        )
    except FeedbackRateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    except FeedbackValidationError as exc:
        return {"ok": False, "detail": str(exc)}
    except FeedbackDeliveryError:
        return {"ok": False, "detail": "Feedback could not be sent right now."}

    return {"ok": True}
