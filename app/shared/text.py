from __future__ import annotations


def build_full_name(first_name: str | None, last_name: str | None) -> str:
    parts = [part.strip() for part in (first_name or "", last_name or "") if part and part.strip()]
    return " ".join(parts) or "Unknown volunteer"


def normalize_search_query(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.lower().split())
    return normalized or None
