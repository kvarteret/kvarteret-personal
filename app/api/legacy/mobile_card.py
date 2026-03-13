from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.dependencies import get_mobile_card_service
from app.services.mobile_card import (
    MobileCardDuplicatePersonError,
    MobileCardInvalidAccessCodeError,
    MobileCardPersonNotFoundError,
    MobileCardService,
)


class LegacyDigitalInternKortRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    accessToken: str | None = None


router = APIRouter()


@router.post("/RequestAccessTokenOnEmail")
async def request_access_token_on_email(
    payload: LegacyDigitalInternKortRequest,
    service: MobileCardService = Depends(get_mobile_card_service),
) -> dict[str, str]:
    try:
        await service.request_access_code(payload.email)
    except MobileCardPersonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MobileCardDuplicatePersonError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/GetInternkortInformation")
async def get_internkort_information(
    payload: LegacyDigitalInternKortRequest,
    service: MobileCardService = Depends(get_mobile_card_service),
) -> dict:
    try:
        session = await service.create_session(payload.email, payload.accessToken or "")
    except MobileCardInvalidAccessCodeError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except MobileCardPersonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return session.card.to_legacy_dict()
