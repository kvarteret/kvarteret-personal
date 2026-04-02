from __future__ import annotations

from datetime import date, datetime


def coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def require_datetime(value: datetime | str | None) -> datetime:
    normalized = coerce_datetime(value)
    if normalized is None:
        raise ValueError("Expected datetime value.")
    return normalized


def coerce_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)
