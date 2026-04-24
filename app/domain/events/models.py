from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


EventLanguage = Literal["no", "en"]
EventStatus = Literal["published", "draft", "archived"]


class EventTranslation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool = True
    title: str
    description: str | None = None
    image_caption: str | None = None


class EventTranslations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    no: EventTranslation | None = None
    en: EventTranslation | None = None


class EventType(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    slug: str
    name: str
    description: str | None = None
    taxonomy_group: str
    sort_order: int
    is_active: bool


class EventOrganizerGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    slug: str
    name: str
    sort_order: int
    is_active: bool
    default_event_type_id: str | None = None


class EventRoom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    slug: str
    name: str
    sort_order: int
    is_active: bool


class EventDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    slug: str
    status: EventStatus
    starts_at: datetime
    ends_at: datetime
    created_at: datetime
    updated_at: datetime
    language: EventLanguage
    title: str
    description: str | None = None
    image_caption: str | None = None
    translations: EventTranslations
    ticket_url: str | None = None
    facebook_url: str | None = None
    image_url: str | None = None
    price: str | None = None
    event_type_id: str
    event_type: EventType | None = None
    room_id: str | None = None
    room_text: str | None = None
    room: EventRoom | None = None
    organizer_groups: list[EventOrganizerGroup]
    is_internal: bool
    is_featured: bool
    recurring_interval_days: int | None = None


class EventList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[EventDetail]


class EventTypeGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    event_types: list[EventType]


class EventTaxonomy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type_groups: list[EventTypeGroup]
    organizer_groups: list[EventOrganizerGroup]
    rooms: list[EventRoom]
