from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class BookingSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    doors_open: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    doors_close: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class BookingSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    submission_id: UUID
    kind: Literal["room", "karaoke"]
    event_name: str = Field(min_length=1, max_length=500)
    contact_name: str = Field(min_length=1, max_length=200)
    contact_email: EmailStr
    room_ids: list[int] = Field(min_length=1, max_length=50)
    schedule: list[BookingSchedule] = Field(min_length=1, max_length=366)
    form: dict[str, object]
    crescat_payload: dict[str, object]


class BookingReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    booking_request_id: UUID
    submission_id: UUID
    content_hash: str
