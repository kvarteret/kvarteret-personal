from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from app.dependencies import get_events_service, get_mobile_card_service
from app.domain.events import (
    EventAuthorization,
    EventDetail,
    EventList,
    EventNotFoundError,
    EventTaxonomy,
    EventsService,
    resolve_event_locale,
)
from app.domain.mobile_card.service import (
    MobileCardInvalidAccessCodeError,
    MobileCardService,
)

router = APIRouter()


@router.get(
    "",
    response_model=EventList,
    operation_id="listEvents",
)
async def list_events(
    response: Response,
    include_internal: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    accept_language: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    events_service: EventsService = Depends(get_events_service),
    mobile_card_service: MobileCardService = Depends(get_mobile_card_service),
) -> EventList:
    locale = resolve_event_locale(accept_language)
    auth = await _resolve_event_authorization(
        authorization=authorization,
        include_internal=include_internal,
        mobile_card_service=mobile_card_service,
    )
    _set_localized_headers(response, locale)
    return await events_service.list_events(
        authorization=auth,
        locale=locale,
        include_internal=include_internal,
        limit=limit,
    )


@router.get(
    "/taxonomy",
    response_model=EventTaxonomy,
    operation_id="getEventTaxonomy",
)
async def get_event_taxonomy(
    events_service: EventsService = Depends(get_events_service),
) -> EventTaxonomy:
    return await events_service.get_taxonomy()


@router.get(
    "/{event_id}",
    response_model=EventDetail,
    operation_id="getEvent",
)
async def get_event(
    event_id: UUID,
    response: Response,
    accept_language: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    events_service: EventsService = Depends(get_events_service),
    mobile_card_service: MobileCardService = Depends(get_mobile_card_service),
) -> EventDetail:
    locale = resolve_event_locale(accept_language)
    auth = await _resolve_event_authorization(
        authorization=authorization,
        include_internal=False,
        mobile_card_service=mobile_card_service,
    )
    try:
        event = await events_service.get_event(
            event_id=event_id,
            authorization=auth,
            locale=locale,
        )
    except EventNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        ) from exc
    _set_localized_headers(response, event.language)
    return event


async def _resolve_event_authorization(
    *,
    authorization: str | None,
    include_internal: bool,
    mobile_card_service: MobileCardService,
) -> EventAuthorization:
    if not authorization:
        if include_internal:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token.",
            )
        return EventAuthorization(can_view_internal=False)
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
        )

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
        )

    try:
        await mobile_card_service.get_current_card(token)
    except MobileCardInvalidAccessCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
        ) from exc
    return EventAuthorization(can_view_internal=True)


def _set_localized_headers(response: Response, locale: str) -> None:
    response.headers["Content-Language"] = locale
    response.headers["Vary"] = "Accept-Language, Authorization"
