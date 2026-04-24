from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict
from fastapi.responses import PlainTextResponse

from app.dependencies import get_mobile_card_service
from app.domain.mobile_card.service import (
    MobileCardDuplicatePersonError,
    MobileCardInvalidAccessCodeError,
    MobileCardPersonNotFoundError,
    MobileCardRateLimitedError,
    MobileCardService,
)
from app.observability import client_ip_from_request


class LegacyDigitalInternKortRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    accessToken: str | None = None


router = APIRouter()


@router.post(
    "/RequestAccessTokenOnEmail",
    response_model=None,
    operation_id="legacyRequestMobileCardAccessTokenOnEmail",
    deprecated=True,
)
async def request_access_token_on_email(
    request: Request,
    payload: LegacyDigitalInternKortRequest,
    service: MobileCardService = Depends(get_mobile_card_service),
) -> dict[str, str] | PlainTextResponse:
    try:
        await service.request_access_code(
            payload.email, source_key=client_ip_from_request(request)
        )
    except (MobileCardPersonNotFoundError, MobileCardDuplicatePersonError):
        return {"status": "ok"}
    except MobileCardRateLimitedError as exc:
        return PlainTextResponse(
            str(exc), status_code=status.HTTP_429_TOO_MANY_REQUESTS
        )
    return {"status": "ok"}


@router.post(
    "/GetInternkortInformation",
    response_model=None,
    operation_id="legacyGetMobileCardInformation",
    deprecated=True,
)
async def get_internkort_information(
    request: Request,
    payload: LegacyDigitalInternKortRequest,
    service: MobileCardService = Depends(get_mobile_card_service),
) -> dict | PlainTextResponse:
    try:
        session = await service.create_session(
            payload.email,
            payload.accessToken or "",
            source_key=client_ip_from_request(request),
        )
    except MobileCardInvalidAccessCodeError:
        return PlainTextResponse(
            "Invalid email or access code.", status_code=status.HTTP_401_UNAUTHORIZED
        )
    except MobileCardPersonNotFoundError:
        return PlainTextResponse(
            "Invalid email or access code.", status_code=status.HTTP_401_UNAUTHORIZED
        )
    except MobileCardRateLimitedError as exc:
        return PlainTextResponse(
            str(exc), status_code=status.HTTP_429_TOO_MANY_REQUESTS
        )
    return session.card.to_legacy_dict()
