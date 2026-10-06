from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from fastapi.responses import JSONResponse

from app.api.booking_request_auth import require_signed_booking
from app.db.session import commit_request_session, rollback_request_session
from app.domain.booking_requests.models import (
    BookingReceipt,
    BookingSnapshot,
    BookingPrefillLookup,
    BookingEventPrefill,
)
from app.domain.booking_requests.repository import BookingRequestsRepository
from app.domain.booking_requests.service import BookingRequestsService

router = APIRouter()

# OpenAPI references resolve from the document root, not this nested schema.
# Inline the only nested model rather than emitting unresolved #/$defs refs.
snapshot_schema = BookingSnapshot.model_json_schema()
snapshot_schema["properties"]["schedule"]["items"] = snapshot_schema.pop("$defs")[
    "BookingSchedule"
]


@router.post(
    "",
    response_model=BookingReceipt,
    status_code=201,
    operation_id="storeBookingRequest",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": snapshot_schema}},
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


@router.post(
    "/prefill",
    response_model=BookingEventPrefill,
    operation_id="getBookingEventPrefill",
    responses={
        401: {"description": "Invalid signature"},
        404: {"description": "Booking not found"},
        503: {"description": "Storage unavailable"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": BookingPrefillLookup.model_json_schema()}
            },
        }
    },
)
async def get_booking_event_prefill(verified=Depends(require_signed_booking)):
    raw, submission_id = verified
    try:
        lookup = BookingPrefillLookup.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "Invalid booking lookup.") from None
    try:
        data = await BookingRequestsRepository().get_snapshot(
            lookup.booking_request_id, submission_id
        )
        if data is None or data.get("kind") != "room":
            raise HTTPException(404, "Booking not found.")
        snapshot = BookingSnapshot.model_validate(data)
        form = snapshot.form
        result = BookingEventPrefill(
            event_name=snapshot.event_name,
            contact_name=snapshot.contact_name,
            contact_email=snapshot.contact_email,
            room_ids=snapshot.room_ids,
            schedule=snapshot.schedule,
            description=form.get("description", ""),
            student_org_name=form.get("studentOrgName", ""),
            free_or_paid=form.get("freeOrPaid", "Gratis"),
            ticket_types=form.get("ticketTypes", []),
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Booking storage unavailable.") from None
    return JSONResponse(
        result.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
    )
