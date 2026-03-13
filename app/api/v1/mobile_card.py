from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr

from app.services.mobile_card import (
    MobileCardDuplicatePersonError,
    MobileCardInvalidAccessCodeError,
    MobileCardPersonNotFoundError,
    MobileCardResponse,
    get_mobile_card_service,
)


class AccessCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class MobileCardSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    access_code: str


class MobileCardSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_token: str
    card: MobileCardResponse


router = APIRouter()


def _get_mobile_card_service_for_request(request: Request):
    if getattr(request.app.state, "mobile_card_service", None) is not None:
        return request.app.state.mobile_card_service
    return get_mobile_card_service()


@router.post("/access-codes", status_code=status.HTTP_202_ACCEPTED)
async def request_access_code(
    request: Request,
    payload: AccessCodeRequest,
) -> dict[str, str]:
    service = _get_mobile_card_service_for_request(request)
    try:
        await service.request_access_code(str(payload.email))
    except MobileCardPersonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MobileCardDuplicatePersonError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"status": "accepted"}


@router.post("/sessions", response_model=MobileCardSessionResponse)
async def create_session(
    request: Request,
    payload: MobileCardSessionCreateRequest,
) -> MobileCardSessionResponse:
    service = _get_mobile_card_service_for_request(request)
    try:
        session = await service.create_session(str(payload.email), payload.access_code)
    except MobileCardInvalidAccessCodeError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except MobileCardPersonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MobileCardSessionResponse(session_token=session.session_token, card=session.card)


@router.get("/me", response_model=MobileCardResponse)
async def get_current_card(
    request: Request,
    authorization: str | None = Header(default=None),
) -> MobileCardResponse:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1]
    service = _get_mobile_card_service_for_request(request)
    try:
        return await service.get_current_card(token)
    except MobileCardInvalidAccessCodeError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
