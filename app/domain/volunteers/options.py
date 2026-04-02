from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GenderOption:
    code: str
    label: str


GENDER_OPTIONS = (
    GenderOption(code="M", label="Mann"),
    GenderOption(code="K", label="Kvinne"),
    GenderOption(code="A", label="Annet"),
)

GENDER_LABELS = {option.code: option.label for option in GENDER_OPTIONS}

SEMESTER_TERM_OPTIONS = (
    ("1", "Vår"),
    ("2", "Høst"),
)


def normalize_gender_code(value: str | None) -> str:
    normalized = (value or "").strip().upper()
    if normalized in GENDER_LABELS:
        return normalized
    return "A"


def gender_label(value: str | None) -> str:
    return GENDER_LABELS.get(normalize_gender_code(value), "Annet")
