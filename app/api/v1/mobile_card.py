from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr

from app.dependencies import get_mobile_card_service
from app.domain.mobile_card.service import (
    MobileCardCurrentCardResult,
    MobileCardDuplicatePersonError,
    MobileCardInvalidAccessCodeError,
    MobileCardPersonNotFoundError,
    MobileCardRateLimitedError,
    MobileCardResponse,
    MobileCardService,
)
from app.observability import client_ip_from_request

logger = logging.getLogger("app.audit")


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


class MobileCardSessionLogoutEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_version: str | None = None
    auth_error_code: str | None = None
    auth_error_message: str | None = None
    auth_error_status: int | None = None
    cached_user_id: int | None = None
    event_name: Literal["credentials_missing_after_login", "session_invalidated"]
    execution_environment: str | None = None
    had_cached_user: bool
    had_login_marker: bool
    had_stored_credentials: bool
    occurred_at: str
    platform: str
    runtime_version: str | None = None
    update_channel: str | None = None
    update_id: str | None = None


class AcceptedStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted"]


router = APIRouter()


@router.post(
    "/access-codes",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedStatusResponse,
    operation_id="requestMobileCardAccessCode",
)
async def request_access_code(
    request: Request,
    payload: AccessCodeRequest,
    service: MobileCardService = Depends(get_mobile_card_service),
) -> AcceptedStatusResponse:
    try:
        await service.request_access_code(
            str(payload.email), source_key=client_ip_from_request(request)
        )
    except (MobileCardPersonNotFoundError, MobileCardDuplicatePersonError):
        return AcceptedStatusResponse(status="accepted")
    except MobileCardRateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    return AcceptedStatusResponse(status="accepted")


@router.post(
    "/sessions",
    response_model=MobileCardSessionResponse,
    response_model_exclude_none=True,
    operation_id="createMobileCardSession",
)
async def create_session(
    request: Request,
    payload: MobileCardSessionCreateRequest,
    # TODO(mobile-card-compat): Remove include_role_history compatibility gate once all supported mobile app versions use lenient backend-response Zod schemas. Additive backend fields must never be default-blocked after that.
    include_role_history: bool = False,
    service: MobileCardService = Depends(get_mobile_card_service),
) -> MobileCardSessionResponse:
    try:
        session = await service.create_session(
            str(payload.email),
            payload.access_code,
            include_role_history=include_role_history,
            source_key=client_ip_from_request(request),
        )
    except MobileCardInvalidAccessCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or access code.",
        ) from exc
    except MobileCardPersonNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or access code.",
        ) from exc
    except MobileCardRateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    return MobileCardSessionResponse(
        session_token=session.session_token, card=session.card
    )


@router.get(
    "/me",
    response_model=MobileCardResponse,
    response_model_exclude_none=True,
    operation_id="getCurrentMobileCard",
)
async def get_current_card(
    response: Response,
    authorization: str | None = Header(default=None),
    # TODO(mobile-card-compat): Remove include_role_history compatibility gate once all supported mobile app versions use lenient backend-response Zod schemas. Additive backend fields must never be default-blocked after that.
    include_role_history: bool = False,
    service: MobileCardService = Depends(get_mobile_card_service),
) -> MobileCardResponse:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token."
        )
    token = authorization.split(" ", 1)[1]
    try:
        card_result: MobileCardCurrentCardResult = await service.get_current_card(
            token, include_role_history=include_role_history
        )
    except MobileCardInvalidAccessCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    if card_result.renewed_session_token:
        response.headers["X-Mobile-Card-Session-Token"] = (
            card_result.renewed_session_token
        )
    return card_result.card


@router.post(
    "/client-events/session-logout",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedStatusResponse,
    operation_id="logMobileCardSessionLogoutEvent",
)
async def log_client_session_logout_event(
    request: Request,
    payload: MobileCardSessionLogoutEventRequest,
) -> AcceptedStatusResponse:
    logger.info(
        "mobile-card client session logout event",
        extra={
            "event": "mobile_card.client_session_logout",
            "event_data": {
                **payload.model_dump(),
                "client_ip": client_ip_from_request(request),
                "user_agent": request.headers.get("user-agent"),
            },
        },
    )
    return AcceptedStatusResponse(status="accepted")
