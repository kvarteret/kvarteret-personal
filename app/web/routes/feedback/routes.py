from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from app.dependencies import get_current_user, get_feedback_service
from app.domain.feedback.service import FeedbackService, FeedbackValidationError
from app.web.templates import templates

router = APIRouter()

FEEDBACK_CATEGORIES = (
    ("ris", "Ris"),
    ("ros", "Ros"),
    ("forslag", "Forslag"),
)


@router.get("/feedback/panel", response_class=HTMLResponse)
async def feedback_panel(
    request: Request,
    page: str | None = None,
    current_user=Depends(get_current_user),
):
    return _render_feedback_panel(
        request,
        page=page or request.headers.get("HX-Current-URL") or "/",
        status="idle",
        name=current_user.display_name or current_user.username if current_user else None,
        email=current_user.email if current_user else None,
    )


@router.get("/feedback/dismiss", response_class=HTMLResponse)
async def feedback_dismiss() -> str:
    return ""


@router.post("/feedback", response_class=HTMLResponse)
async def feedback_submit(
    request: Request,
    category: str = Form(...),
    name: str | None = Form(default=None),
    email: str | None = Form(default=None),
    message: str = Form(...),
    page: str = Form(...),
    feedback_service: FeedbackService = Depends(get_feedback_service),
):
    try:
        await feedback_service.submit_feedback(
            category=category,
            name=name,
            email=email,
            message=message,
            page=page,
        )
    except FeedbackValidationError as exc:
        return _render_feedback_panel(
            request,
            page=page,
            status="error",
            message_text=str(exc),
            category=category,
            name=name,
            email=email,
            feedback_message=message,
        )
    return _render_feedback_panel(
        request,
        page=page,
        status="success",
        message_text="Melding sendt.",
        category="ros",
        name=name,
        email=email,
    )


def _render_feedback_panel(
    request: Request,
    *,
    page: str,
    status: str,
    message_text: str | None = None,
    category: str = "ros",
    name: str | None = None,
    email: str | None = None,
    feedback_message: str = "",
):
    return templates.TemplateResponse(
        request,
        "components/feedback/feedback_panel.html",
        {
            "page": page,
            "feedback_categories": FEEDBACK_CATEGORIES,
            "feedback_status": status,
            "feedback_status_message": message_text,
            "feedback_category": category,
            "feedback_name": name or "",
            "feedback_email": email or "",
            "feedback_message": feedback_message,
        },
    )
