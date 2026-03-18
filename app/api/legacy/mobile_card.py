from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from fastapi.responses import PlainTextResponse

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


@router.post("/RequestAccessTokenOnEmail", response_model=None)
async def request_access_token_on_email(
    payload: LegacyDigitalInternKortRequest,
    service: MobileCardService = Depends(get_mobile_card_service),
) -> dict[str, str] | PlainTextResponse:
    try:
        await service.request_access_code(payload.email)
    except MobileCardPersonNotFoundError as exc:
        return PlainTextResponse(str(exc), status_code=status.HTTP_404_NOT_FOUND)
    except MobileCardDuplicatePersonError as exc:
        return PlainTextResponse(str(exc), status_code=status.HTTP_409_CONFLICT)
    return {"status": "ok"}


@router.post("/GetInternkortInformation", response_model=None)
async def get_internkort_information(
    payload: LegacyDigitalInternKortRequest,
    service: MobileCardService = Depends(get_mobile_card_service),
) -> dict | PlainTextResponse:
    try:
        session = await service.create_session(payload.email, payload.accessToken or "")
    except MobileCardInvalidAccessCodeError as exc:
        return PlainTextResponse(str(exc), status_code=status.HTTP_401_UNAUTHORIZED)
    except MobileCardPersonNotFoundError as exc:
        return PlainTextResponse(str(exc), status_code=status.HTTP_404_NOT_FOUND)
    return session.card.to_legacy_dict()
