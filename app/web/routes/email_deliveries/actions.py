from __future__ import annotations

from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status

from app.db.session import commit_request_session
from app.dependencies import get_email_outbox_service, require_admin_user
from app.email_outbox_service import (
    EmailDeliveryConflictError,
    EmailDeliveryNotFoundError,
    EmailOutboxService,
    RecipientCorrectionError,
)
from app.observability import log_admin_activity
from app.web.route_helpers import redirect_to

router = APIRouter(include_in_schema=False)


@router.post("/email-deliveries/{delivery_id}/retry")
async def email_delivery_retry(
    request: Request,
    delivery_id: UUID,
    current_user=Depends(require_admin_user),
    service: EmailOutboxService = Depends(get_email_outbox_service),
):
    actor_id = _actor_id(current_user)
    try:
        successor_id = await service.retry_failed(
            delivery_id, actor_user_account_id=actor_id
        )
        await commit_request_session()
        await _dispatch_best_effort(service)
    except EmailDeliveryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except EmailDeliveryConflictError as exc:
        return _error_redirect(delivery_id, str(exc))
    log_admin_activity(
        request=request,
        user=current_user,
        action="email_delivery.retry",
        subject_type="email_delivery",
        subject_id=str(successor_id),
        details={"email_delivery_id": successor_id},
    )
    return redirect_to(f"/email-deliveries/{successor_id}")


@router.post("/email-deliveries/{delivery_id}/correct-recipient")
async def email_delivery_correct_recipient(
    request: Request,
    delivery_id: UUID,
    recipient_email: str = Form(...),
    current_user=Depends(require_admin_user),
    service: EmailOutboxService = Depends(get_email_outbox_service),
):
    actor_id = _actor_id(current_user)
    try:
        successor_id = await service.correct_volunteer_recipient(
            delivery_id,
            recipient_email=recipient_email,
            actor_user_account_id=actor_id,
        )
        await commit_request_session()
        await _dispatch_best_effort(service)
    except EmailDeliveryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except (EmailDeliveryConflictError, RecipientCorrectionError) as exc:
        return _error_redirect(delivery_id, str(exc))
    log_admin_activity(
        request=request,
        user=current_user,
        action="email_delivery.correct_recipient",
        subject_type="email_delivery",
        subject_id=str(successor_id),
        details={"email_delivery_id": successor_id},
    )
    return redirect_to(f"/email-deliveries/{successor_id}")


async def _dispatch_best_effort(service: EmailOutboxService) -> None:
    try:
        await service.dispatch_due(batch_size=10)
    except Exception:
        # The committed successor remains available to cron.
        return


def _actor_id(current_user) -> int:
    if current_user.user_account_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return current_user.user_account_id


def _error_redirect(delivery_id: UUID, message: str):
    return redirect_to(
        f"/email-deliveries/{delivery_id}?error={quote_plus(message)}"
    )
