from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_email_outbox_service, require_admin_user
from app.email_outbox_service import EmailOutboxService
from app.observability import log_admin_activity
from app.web.templates import templates

router = APIRouter(include_in_schema=False)
_VALID_STATUSES = {"pending", "sent", "failed", "expired", "cancelled"}


@router.get("/email-deliveries")
async def email_deliveries_index(
    request: Request,
    delivery_status: str = "failed",
    template_key: str | None = None,
    created_after: str | None = None,
    error: str | None = None,
    current_user=Depends(require_admin_user),
    service: EmailOutboxService = Depends(get_email_outbox_service),
):
    selected_status = (
        delivery_status if delivery_status in _VALID_STATUSES else None
    )
    parsed_created_after = _parse_date(created_after)
    deliveries = await service.list_deliveries(
        status=selected_status,
        template_key=template_key,
        created_after=parsed_created_after,
    )
    log_admin_activity(
        request=request,
        user=current_user,
        action="email_delivery.list",
        subject_type="email_delivery",
        details={"status": selected_status, "count": len(deliveries)},
    )
    return templates.TemplateResponse(
        request,
        "pages/email_deliveries/email_deliveries_index.html",
        {
            "title": "E-postleveranser",
            "section": "email-deliveries",
            "current_user": current_user,
            "deliveries": deliveries,
            "selected_status": selected_status or "all",
            "template_key": template_key or "",
            "created_after": created_after or "",
            "error_message": error,
        },
    )


@router.get("/email-deliveries/{delivery_id}")
async def email_delivery_detail(
    request: Request,
    delivery_id: UUID,
    error: str | None = None,
    current_user=Depends(require_admin_user),
    service: EmailOutboxService = Depends(get_email_outbox_service),
):
    detail = await service.get_delivery(delivery_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email delivery was not found.",
        )
    log_admin_activity(
        request=request,
        user=current_user,
        action="email_delivery.view",
        subject_type="email_delivery",
        subject_id=str(delivery_id),
    )
    return templates.TemplateResponse(
        request,
        "pages/email_deliveries/email_delivery_detail.html",
        {
            "title": "E-postleveranse",
            "section": "email-deliveries",
            "current_user": current_user,
            "detail": detail,
            "error_message": error,
        },
    )


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
