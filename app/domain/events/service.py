from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.domain.events.models import (
    EventDetail,
    EventLanguage,
    EventList,
    EventOrganizerGroup,
    EventRoom,
    EventTaxonomy,
    EventTranslation,
    EventTranslations,
    EventType,
    EventTypeGroup,
)
from app.domain.events.repository import EventsRepository

TAXONOMY_GROUP_ORDER = ["Musikk", "Scenekunst", "Faglig", "Sosialt", "Organisasjon"]
_EVENT_NOT_FOUND = "Event not found."


class EventNotFoundError(RuntimeError):
    pass


class InvalidEventAuthorizationError(RuntimeError):
    pass


@dataclass(slots=True)
class EventAuthorization:
    can_view_internal: bool = False


class EventsService:
    def __init__(self, repository: EventsRepository) -> None:
        self.repository = repository

    async def list_events(
        self,
        *,
        authorization: EventAuthorization,
        locale: EventLanguage,
        include_internal: bool = False,
        limit: int = 30,
    ) -> EventList:
        bounded_limit = _bound_limit(limit)
        rows = await self.repository.list_events(
            include_internal=include_internal and authorization.can_view_internal,
            now=datetime.now(UTC),
            fetch_limit=min(bounded_limit * 3, 300),
        )
        events = [
            mapped
            for row in rows
            if (mapped := _map_event_row(row, locale=locale)) is not None
        ]
        return EventList(events=events[:bounded_limit])

    async def get_event(
        self,
        *,
        event_id: UUID,
        authorization: EventAuthorization,
        locale: EventLanguage,
    ) -> EventDetail:
        row = await self.repository.get_event(event_id)
        if row is None:
            raise EventNotFoundError(_EVENT_NOT_FOUND)
        _validate_event_visible(row, authorization)
        event = _map_event_row(row, locale=locale)
        if event is None:
            raise EventNotFoundError(_EVENT_NOT_FOUND)
        return event

    async def get_taxonomy(self) -> EventTaxonomy:
        event_types = [
            _map_event_type(row) for row in await self.repository.list_event_types()
        ]
        organizer_groups = [
            _map_organizer_group(row)
            for row in await self.repository.list_organizer_groups()
        ]
        rooms = [_map_room(row) for row in await self.repository.list_rooms()]

        grouped: dict[str, list[EventType]] = {}
        for event_type in event_types:
            grouped.setdefault(event_type.taxonomy_group, []).append(event_type)

        group_names = [
            *[name for name in TAXONOMY_GROUP_ORDER if name in grouped],
            *sorted(name for name in grouped if name not in TAXONOMY_GROUP_ORDER),
        ]
        return EventTaxonomy(
            event_type_groups=[
                EventTypeGroup(name=name, event_types=grouped[name])
                for name in group_names
            ],
            organizer_groups=organizer_groups,
            rooms=rooms,
        )


def _validate_event_visible(
    row: dict[str, Any], authorization: EventAuthorization
) -> None:
    if row["status"] != "published":
        raise EventNotFoundError(_EVENT_NOT_FOUND)
    if row["is_internal"] and not authorization.can_view_internal:
        raise EventNotFoundError(_EVENT_NOT_FOUND)
    if row["event_end"] is not None and row["event_end"] < datetime.now(UTC):
        raise EventNotFoundError(_EVENT_NOT_FOUND)


def resolve_event_locale(accept_language: str | None) -> EventLanguage:
    if not accept_language:
        return "no"
    parsed = _parse_accept_language(accept_language)
    return _pick_locale_from_parsed(parsed)


def _parse_accept_language(header: str) -> list[tuple[str, float, int]]:
    preferences: list[tuple[str, float, int]] = []
    for index, part in enumerate(header.split(",")):
        token = part.strip()
        if not token:
            continue
        language_range, *params = [segment.strip() for segment in token.split(";")]
        quality = 1.0
        for param in params:
            if not param.startswith("q="):
                continue
            try:
                quality = float(param[2:])
            except ValueError:
                quality = 0.0
        preferences.append((language_range.lower(), quality, index))
    return preferences


def _pick_locale_from_parsed(
    preferences: list[tuple[str, float, int]],
) -> EventLanguage:
    for language_range, _quality, _index in sorted(
        preferences, key=lambda item: (-item[1], item[2])
    ):
        primary = language_range.split("-", 1)[0]
        if primary in {"no", "nb", "nn"}:
            return "no"
        if primary == "en":
            return "en"
    return "no"


def _bound_limit(limit: int) -> int:
    return max(1, min(limit, 100))


def _map_event_row(row: dict[str, Any], *, locale: EventLanguage) -> EventDetail | None:
    translations = _map_translations(row["translations"])
    selected_language, selected_translation = _select_translation(translations, locale)
    if selected_translation is None:
        return None
    return EventDetail(
        id=str(row["id"]),
        slug=row["slug"],
        status=row["status"],
        starts_at=row["event_start"],
        ends_at=row["event_end"],
        created_at=row["created_at"],
        updated_at=row["updated_at"] or row["created_at"],
        language=selected_language,
        title=selected_translation.title,
        description=selected_translation.description,
        image_caption=selected_translation.image_caption,
        translations=translations,
        ticket_url=row["ticket_url"],
        facebook_url=row["facebook_url"],
        image_url=row["image_url"],
        price=row["price"],
        event_type_id=str(row["event_type_id"]),
        event_type=_map_prefixed_event_type(row),
        room_id=str(row["room_id"]) if row["room_id"] else None,
        room_text=row["room_text"],
        room=_map_prefixed_room(row),
        organizer_groups=[
            _map_organizer_group(group) for group in row["organizer_groups"]
        ],
        is_internal=row["is_internal"],
        is_featured=row["is_featured"],
        recurring_interval_days=row["recurring_interval_days"],
    )


def _map_translations(value: Any) -> EventTranslations:
    if not isinstance(value, dict):
        return EventTranslations()
    return EventTranslations(
        no=_map_translation(value.get("no")),
        en=_map_translation(value.get("en")),
    )


def _map_translation(value: Any) -> EventTranslation | None:
    if not isinstance(value, dict):
        return None
    title = str(value.get("title") or "").strip()
    if not title:
        return None
    return EventTranslation(
        available=bool(value.get("available", True)),
        title=title,
        description=value.get("description"),
        image_caption=value.get("image_caption"),
    )


def _select_translation(
    translations: EventTranslations,
    locale: EventLanguage,
) -> tuple[EventLanguage, EventTranslation | None]:
    preferred = getattr(translations, locale)
    if preferred is not None:
        return locale, preferred
    fallback_locale: EventLanguage = "en" if locale == "no" else "no"
    fallback = getattr(translations, fallback_locale)
    return fallback_locale, fallback


def _map_event_type(row: dict[str, Any]) -> EventType:
    return EventType(
        id=str(row["id"]),
        slug=row["slug"],
        name=row["name"],
        description=row["description"],
        taxonomy_group=row["taxonomy_group"],
        sort_order=row["sort_order"],
        is_active=row["is_active"],
    )


def _map_prefixed_event_type(row: dict[str, Any]) -> EventType | None:
    if row["event_type__id"] is None:
        return None
    return EventType(
        id=str(row["event_type__id"]),
        slug=row["event_type__slug"],
        name=row["event_type__name"],
        description=row["event_type__description"],
        taxonomy_group=row["event_type__taxonomy_group"],
        sort_order=row["event_type__sort_order"],
        is_active=row["event_type__is_active"],
    )


def _map_organizer_group(row: dict[str, Any]) -> EventOrganizerGroup:
    return EventOrganizerGroup(
        id=str(row["id"]),
        slug=row["slug"],
        name=row["name"],
        sort_order=row["sort_order"],
        is_active=row["is_active"],
        default_event_type_id=str(row["default_event_type_id"])
        if row["default_event_type_id"]
        else None,
    )


def _map_room(row: dict[str, Any]) -> EventRoom:
    return EventRoom(
        id=str(row["id"]),
        slug=row["slug"],
        name=row["name"],
        sort_order=row["sort_order"],
        is_active=row["is_active"],
    )


def _map_prefixed_room(row: dict[str, Any]) -> EventRoom | None:
    if row["room__id"] is None:
        return None
    return EventRoom(
        id=str(row["room__id"]),
        slug=row["room__slug"],
        name=row["room__name"],
        sort_order=row["room__sort_order"],
        is_active=row["room__is_active"],
    )
