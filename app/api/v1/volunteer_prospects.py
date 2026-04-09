from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from app.dependencies import get_volunteer_applications_service
from app.domain.volunteer_applications.service import (
    PublicProspectRegistrationInput,
    VolunteerAlreadyExistsError,
    VolunteerApplicationConflictError,
    VolunteerApplicationValidationError,
    VolunteerApplicationsService,
)

router = APIRouter()


class PublicVolunteerProspectRequest(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    study_institution: str
    background_details: str | None = None
    first_choice_group_slug: str
    second_choice_group_slug: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
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
            ),
            base_url=str(request.base_url).rstrip("/"),
        )
    except VolunteerAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"En frivillig med denne e-postadressen finnes allerede (id={exc.volunteer_id}).",
        ) from exc
    except VolunteerApplicationValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except VolunteerApplicationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"registrationId": detail.registration_id}
