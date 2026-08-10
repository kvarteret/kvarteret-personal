from __future__ import annotations

import re
from dataclasses import dataclass

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat

DEFAULT_PHONE_REGION = "NO"
NORWEGIAN_PHONE_FALLBACK = "+4700000000"

_WHITESPACE_RE = re.compile(r"\s+")
_TRUNK_ZERO_RE = re.compile(r"^(\+\d{1,3})\(0\)")
_DIGITS_RE = re.compile(r"\D")
_ALL_ZERO_VALUES = {"0", "00", "000", "0000", "00000", "000000", "0000000", "00000000"}
_KNOWN_PLACEHOLDER_DIGITS = {"2147483647", "12345678", "123456789", "987654321"}


@dataclass(slots=True)
class PhoneNormalizationResult:
    original: str | None
    cleaned: str | None
    normalized: str | None
    status: str
    reason: str


def normalize_phone_number(
    value: str | None, *, default_region: str = DEFAULT_PHONE_REGION
) -> str | None:
    result = analyze_phone_number(value, default_region=default_region)
    if result.status == "empty":
        return None
    if is_obviously_false_phone_number(value):
        return None
    return result.normalized or result.cleaned


def normalize_required_phone_number(
    value: str | None,
    *,
    default_region: str = DEFAULT_PHONE_REGION,
) -> str:
    result = analyze_phone_number(value, default_region=default_region)
    if result.cleaned is None:
        raise ValueError("Telefonnummer er påkrevd.")
    if result.normalized is None:
        raise ValueError("Skriv inn et gyldig telefonnummer.")
    return result.normalized


def require_e164_phone_number(
    value: str | None, *, default_region: str = DEFAULT_PHONE_REGION
) -> str:
    result = analyze_phone_number(value, default_region=default_region)
    if result.cleaned is None:
        raise ValueError("Phone number is required.")
    if result.normalized is None:
        raise ValueError("Phone number must be a valid E.164 number.")
    if result.cleaned != result.normalized:
        raise ValueError(
            "Phone number must be entered in E.164 format, for example +4791234567."
        )
    return result.normalized


def analyze_phone_number(
    value: str | None, *, default_region: str = DEFAULT_PHONE_REGION
) -> PhoneNormalizationResult:
    cleaned = _clean_phone_input(value)
    if cleaned is None:
        return PhoneNormalizationResult(
            original=value,
            cleaned=None,
            normalized=None,
            status="empty",
            reason="empty",
        )

    if any(ch.isalpha() for ch in cleaned):
        return PhoneNormalizationResult(
            original=value,
            cleaned=cleaned,
            normalized=None,
            status="invalid",
            reason="contains_letters",
        )

    if cleaned.startswith("+") and _DIGITS_RE.sub("", cleaned) == "4700000000":
        return PhoneNormalizationResult(
            original=value,
            cleaned=cleaned,
            normalized=NORWEGIAN_PHONE_FALLBACK,
            status="normalized",
            reason="fallback",
        )

    parsed = _parse_phone_number(cleaned, default_region=default_region)
    if parsed is None:
        return PhoneNormalizationResult(
            original=value,
            cleaned=cleaned,
            normalized=None,
            status="invalid",
            reason="unparseable",
        )

    if not phonenumbers.is_possible_number(parsed):
        return PhoneNormalizationResult(
            original=value,
            cleaned=cleaned,
            normalized=None,
            status="invalid",
            reason="not_possible",
        )

    if not phonenumbers.is_valid_number(parsed):
        return PhoneNormalizationResult(
            original=value,
            cleaned=cleaned,
            normalized=None,
            status="invalid",
            reason="not_valid",
        )

    normalized = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    return PhoneNormalizationResult(
        original=value,
        cleaned=cleaned,
        normalized=normalized,
        status="normalized",
        reason="ok",
    )


def is_obviously_false_phone_number(value: str | None) -> bool:
    cleaned = _clean_phone_input(value)
    if cleaned is None:
        return False
    if any(ch.isalpha() for ch in cleaned):
        return True
    digits = _DIGITS_RE.sub("", cleaned)
    lowered = cleaned.lower()
    if lowered in _ALL_ZERO_VALUES:
        return True
    if len(digits) < 8:
        return True
    if digits in _KNOWN_PLACEHOLDER_DIGITS:
        return True
    return len(digits) >= 8 and len(set(digits)) == 1


def _clean_phone_input(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace("\u00a0", " ").replace("\u202f", " ")
    cleaned = cleaned.removeprefix("tel:").removeprefix("TEL:")
    cleaned = _TRUNK_ZERO_RE.sub(r"\1", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned or None


def _parse_phone_number(
    cleaned: str, *, default_region: str
) -> phonenumbers.PhoneNumber | None:
    candidates = _build_parse_candidates(cleaned, default_region=default_region)
    for raw_value, region in candidates:
        try:
            return phonenumbers.parse(raw_value, region)
        except NumberParseException:
            continue
    return None


def _build_parse_candidates(
    cleaned: str, *, default_region: str
) -> list[tuple[str, str | None]]:
    digits = _DIGITS_RE.sub("", cleaned)
    candidates: list[tuple[str, str | None]] = []

    if cleaned.startswith("+"):
        candidates.append((cleaned, None))
        return candidates

    if cleaned.startswith("00") and len(digits) > 2:
        candidates.append((f"+{digits[2:]}", None))
        return candidates

    if digits.isdigit() and len(digits) == 8:
        candidates.append((digits, default_region))
        return candidates

    if digits.startswith("47") and len(digits) == 10:
        candidates.append((f"+{digits}", None))
        return candidates

    # Allow formatting noise on already-international numbers such as "+47 999 99 999".
    if cleaned.startswith(("+", "00")):
        candidates.append((cleaned, None))
        return candidates

    return candidates
