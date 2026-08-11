from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.dependencies import get_volunteer_applications_service
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

router = APIRouter()
logger = logging.getLogger(__name__)


class PublicVolunteerProspectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    email: EmailStr
    phone: str
    study_institution: str
    background_details: str | None = None
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
    friend_emails: list[str] | None = None


class PublicVolunteerProspectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registrationId: int


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=PublicVolunteerProspectResponse,
    operation_id="createPublicVolunteerProspect",
)
async def create_public_volunteer_prospect(
    payload: PublicVolunteerProspectRequest,
    request: Request,
    volunteer_applications_service: VolunteerApplicationsService = Depends(get_volunteer_applications_service),
):
    try:
        detail = await volunteer_applications_service.create_public_prospect_registration(
            PublicProspectRegistrationInput(
                full_name=payload.full_name,
                email=str(payload.email),
                phone=payload.phone,
                study_institution=payload.study_institution,
                background_details=payload.background_details,
                first_choice_group_slug=payload.first_choice_group_slug,
                second_choice_group_slug=payload.second_choice_group_slug,
                friend_emails=payload.friend_emails or [],
            ),
            base_url=str(request.base_url).rstrip("/"),
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
