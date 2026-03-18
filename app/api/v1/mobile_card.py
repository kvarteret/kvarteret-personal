from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr

from app.dependencies import get_mobile_card_service
from app.services.mobile_card import (
    MobileCardDuplicatePersonError,
    MobileCardInvalidAccessCodeError,
    MobileCardPersonNotFoundError,
    MobileCardRateLimitedError,
    MobileCardResponse,
    MobileCardService,
)
from app.observability import client_ip_from_request


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


@router.post("/access-codes", status_code=status.HTTP_202_ACCEPTED)
async def request_access_code(
    request: Request,
    payload: AccessCodeRequest,
    service: MobileCardService = Depends(get_mobile_card_service),
) -> dict[str, str]:
    try:
        await service.request_access_code(str(payload.email), source_key=client_ip_from_request(request))
    except (MobileCardPersonNotFoundError, MobileCardDuplicatePersonError):
        return {"status": "accepted"}
    except MobileCardRateLimitedError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    return {"status": "accepted"}


@router.post("/sessions", response_model=MobileCardSessionResponse)
async def create_session(
    request: Request,
    payload: MobileCardSessionCreateRequest,
    service: MobileCardService = Depends(get_mobile_card_service),
) -> MobileCardSessionResponse:
    try:
        session = await service.create_session(
            str(payload.email),
            payload.access_code,
            source_key=client_ip_from_request(request),
        )
    except MobileCardInvalidAccessCodeError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or access code.") from exc
    except MobileCardPersonNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or access code.") from exc
    except MobileCardRateLimitedError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    return MobileCardSessionResponse(session_token=session.session_token, card=session.card)


@router.get("/me", response_model=MobileCardResponse)
async def get_current_card(
    authorization: str | None = Header(default=None),
    service: MobileCardService = Depends(get_mobile_card_service),
) -> MobileCardResponse:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1]
    try:
        return await service.get_current_card(token)
    except MobileCardInvalidAccessCodeError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
