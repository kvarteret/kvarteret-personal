from __future__ import annotations

from datetime import date, datetime


def build_full_name(first_name: str | None, last_name: str | None) -> str:
    parts = [part.strip() for part in (first_name or "", last_name or "") if part and part.strip()]
    return " ".join(parts) or "Unknown volunteer"


def coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def coerce_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def postgrest_ilike_pattern(value: str) -> str:
    escaped = value.replace(",", "\\,").replace("(", "\\(").replace(")", "\\)")
    return f"*{escaped}*"


def normalize_search_query(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.lower().split())
    return normalized or None
