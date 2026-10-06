from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.api.booking_request_auth import require_signed_booking
from app.db.session import commit_request_session, rollback_request_session
from app.domain.booking_requests.models import BookingReceipt, BookingSnapshot
from app.domain.booking_requests.repository import BookingRequestsRepository
from app.domain.booking_requests.service import BookingRequestsService

router = APIRouter()


@router.post(
    "",
    response_model=BookingReceipt,
    status_code=201,
    operation_id="storeBookingRequest",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": BookingSnapshot.model_json_schema()}
            },
        }
    },
    responses={
        401: {"description": "Invalid signature"},
        413: {"description": "Snapshot too large"},
        429: {"description": "Rate limited"},
        503: {"description": "Storage unavailable"},
    },
)
async def store_booking_request(verified=Depends(require_signed_booking)):
    raw, submission_id = verified
    try:
        snapshot = BookingSnapshot.model_validate_json(raw)
    except ValidationError:
        # Never include submitted contact values in error responses or logs.
        raise HTTPException(422, "Invalid booking snapshot.") from None
    if snapshot.submission_id != submission_id:
        raise HTTPException(401, "Invalid booking authentication.")
    try:
        receipt = await BookingRequestsService(BookingRequestsRepository()).store(
            snapshot
        )
        # A receipt is only valid after durable commit; the website can then
        # safely send the Crescat request without risking loss of this record.
        await commit_request_session()
    except Exception:
        await rollback_request_session()
        raise HTTPException(503, "Booking storage unavailable.") from None
    return receipt
