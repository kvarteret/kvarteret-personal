from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError

from app.api.request_auth import (
    VerifiedVolunteerProspectRequest,
    require_signed_volunteer_prospect,
)
from app.config import Settings
from app.db.rate_limit import RateLimiter, RateLimitExceeded
from app.dependencies import (
    get_rate_limiter,
    get_settings,
    get_volunteer_applications_service,
)
from app.domain.volunteer_applications.service import (
    ActiveVolunteerRegistrationExistsError,
    PublicProspectRegistrationInput,
    VolunteerAlreadyExistsError,
    VolunteerApplicationConflictError,
    VolunteerApplicationFieldConflictError,
    VolunteerApplicationFieldValidationError,
    VolunteerApplicationValidationError,
    VolunteerApplicationsService,
)
from app.observability import current_trace_id, emit_event
from app.shared.phone_numbers import normalize_phone_number

router = APIRouter()
logger = logging.getLogger(__name__)

EmailAddress = Annotated[EmailStr, Field(max_length=254)]


class PublicVolunteerProspectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=201)
    email: EmailAddress
    phone: str = Field(min_length=1, max_length=16)
    study_institution: str = Field(min_length=1, max_length=160)
    background_details: str | None = Field(default=None, max_length=2_000)
    first_choice_group_slug: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    second_choice_group_slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    friend_emails: list[EmailAddress] | None = Field(default=None, max_length=2)


class PublicVolunteerProspectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registrationId: int


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=PublicVolunteerProspectResponse,
    operation_id="createPublicVolunteerProspect",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Missing, invalid, stale, or replayed HMAC authentication."
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "HMAC authentication or replay protection is unavailable."
        },
        status.HTTP_413_CONTENT_TOO_LARGE: {
            "description": "The request body exceeds the configured byte limit."
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "A route-wide, client, or normalized-email limit was exceeded."
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Malformed JSON or a request field failed validation.",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/HTTPValidationError"}
                }
            },
        },
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": PublicVolunteerProspectRequest.model_json_schema(
                        mode="validation"
                    )
                }
            },
        },
        "parameters": [
            {
                "name": "X-Kvarteret-Timestamp",
                "in": "header",
                "required": True,
                "description": "Unix timestamp in seconds used by the HMAC signature.",
                "schema": {"type": "string"},
            },
            {
                "name": "X-Kvarteret-Nonce",
                "in": "header",
                "required": True,
                "description": "Lowercase UUID consumed once to prevent request replay.",
                "schema": {"type": "string", "format": "uuid"},
            },
            {
                "name": "X-Kvarteret-Idempotency-Key",
                "in": "header",
                "required": False,
                "description": (
                    "Canonical lowercase UUID. Required for v2 signatures; "
                    "identical retries return the original registration."
                ),
                "schema": {"type": "string", "format": "uuid"},
            },
            {
                "name": "X-Kvarteret-Client-Key",
                "in": "header",
                "required": False,
                "description": (
                    "Opaque v1 HMAC of the caller IP. Required for v2 signatures; "
                    "the raw IP must not be forwarded."
                ),
                "schema": {"type": "string", "pattern": "^v1=[0-9a-f]{64}$"},
            },
        ]
    },
)
async def create_public_volunteer_prospect(
    request: Request,
    signed_request: VerifiedVolunteerProspectRequest = Depends(
        require_signed_volunteer_prospect
    ),
    settings: Settings = Depends(get_settings),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    try:
        payload = PublicVolunteerProspectRequest.model_validate_json(
            signed_request.body
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.errors(include_input=False, include_url=False),
        ) from exc

    normalized_email = str(payload.email).strip().lower()
    email_key = hmac.new(
        settings.app_secret_key.encode(),
        normalized_email.encode(),
        hashlib.sha256,
    ).hexdigest()
    try:
        await rate_limiter.hit(
            f"volunteer-prospect:email:{email_key}",
            limit=settings.volunteer_prospect_email_limit,
            window_seconds=settings.volunteer_prospect_email_window_seconds,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests.",
            headers={
                "Retry-After": str(settings.volunteer_prospect_email_window_seconds)
            },
        ) from exc
    except Exception as exc:
        logger.exception("Volunteer prospect email rate limiting failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable.",
        ) from exc

    request_hash = _normalized_payload_hash(
        payload,
        secret=settings.app_secret_key,
    )
    try:
        detail = await volunteer_applications_service.create_public_prospect_registration(
            PublicProspectRegistrationInput(
                full_name=payload.full_name,
                email=normalized_email,
                phone=payload.phone,
                study_institution=payload.study_institution,
                background_details=payload.background_details,
                first_choice_group_slug=payload.first_choice_group_slug,
                second_choice_group_slug=payload.second_choice_group_slug,
                friend_emails=[str(email) for email in payload.friend_emails or []],
            ),
            base_url=str(request.base_url).rstrip("/"),
            idempotency_key=signed_request.idempotency_key,
            request_hash=request_hash,
        )
    except VolunteerApplicationFieldValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(exc), "fieldErrors": exc.field_errors},
        ) from exc
    except VolunteerApplicationFieldConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "fieldErrors": exc.field_errors},
        )
    except VolunteerAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="En frivillig med denne e-postadressen finnes allerede.",
        )
    except ActiveVolunteerRegistrationExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="En aktiv søknad med denne e-postadressen finnes allerede.",
        )
    except VolunteerApplicationValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except VolunteerApplicationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    trace_id = current_trace_id()
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("registration_id", detail.registration_id)
    emit_event(
        logger,
        "volunteer.lifecycle",
        fields={
            "registration_id": detail.registration_id,
            "origin_trace_id": trace_id,
            "status": "prospect_registered",
        },
    )
    return PublicVolunteerProspectResponse(registrationId=detail.registration_id)


def _normalized_payload_hash(
    payload: PublicVolunteerProspectRequest,
    *,
    secret: str,
) -> str:
    canonical_payload = {
        "full_name": " ".join(payload.full_name.split()),
        "email": str(payload.email).strip().lower(),
        "phone": normalize_phone_number(payload.phone),
        "study_institution": " ".join(payload.study_institution.split()),
        "background_details": (
            payload.background_details.strip()
            if payload.background_details and payload.background_details.strip()
            else None
        ),
        "first_choice_group_slug": payload.first_choice_group_slug.lower(),
        "second_choice_group_slug": (
            payload.second_choice_group_slug.lower()
            if payload.second_choice_group_slug
            else None
        ),
        "friend_emails": sorted(
            str(email).strip().lower() for email in payload.friend_emails or []
        ),
    }
    encoded = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hmac.new(secret.encode(), encoded, hashlib.sha256).hexdigest()
