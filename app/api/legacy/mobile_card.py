from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from app.services.mobile_card import (
    MobileCardDuplicatePersonError,
    MobileCardInvalidAccessCodeError,
    MobileCardPersonNotFoundError,
    get_mobile_card_service,
)


class LegacyDigitalInternKortRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    accessToken: str | None = None


router = APIRouter()


def _get_mobile_card_service_for_request(request: Request):
    if getattr(request.app.state, "mobile_card_service", None) is not None:
        return request.app.state.mobile_card_service
    return get_mobile_card_service()


@router.post("/RequestAccessTokenOnEmail")
async def request_access_token_on_email(
    app_request: Request,
    payload: LegacyDigitalInternKortRequest,
) -> dict[str, str]:
    service = _get_mobile_card_service_for_request(app_request)
    try:
        await service.request_access_code(payload.email)
    except MobileCardPersonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MobileCardDuplicatePersonError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/GetInternkortInformation")
async def get_internkort_information(
    app_request: Request,
    payload: LegacyDigitalInternKortRequest,
) -> dict:
    service = _get_mobile_card_service_for_request(app_request)
    try:
        session = await service.create_session(payload.email, payload.accessToken or "")
    except MobileCardInvalidAccessCodeError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except MobileCardPersonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return session.card.to_legacy_dict()
