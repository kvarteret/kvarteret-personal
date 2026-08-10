from __future__ import annotations

import pytest

from app.shared.phone_numbers import (
    NORWEGIAN_PHONE_FALLBACK,
    analyze_phone_number,
    is_obviously_false_phone_number,
    normalize_phone_number,
    normalize_required_phone_number,
    require_e164_phone_number,
)


def test_normalize_phone_number_converts_norwegian_local_number_to_e164() -> None:
    assert normalize_phone_number("95230903") == "+4795230903"


def test_normalize_phone_number_converts_00_prefixed_number_to_e164() -> None:
    assert normalize_phone_number("00491756516398") == "+491756516398"


def test_normalize_phone_number_nulls_obviously_false_value() -> None:
    assert normalize_phone_number("lukas.marx@imbrsea.eu") is None


def test_normalize_phone_number_preserves_ambiguous_invalid_value_for_manual_review() -> None:
    assert normalize_phone_number("85751824") == "85751824"


def test_analyze_phone_number_marks_invalid_values_for_manual_review() -> None:
    result = analyze_phone_number("2147483647")

    assert result.status == "invalid"
    assert result.normalized is None
    assert result.reason in {"unparseable", "not_possible", "not_valid"}


def test_is_obviously_false_phone_number_detects_placeholder_number() -> None:
    assert is_obviously_false_phone_number("11111111") is True


def test_require_e164_phone_number_accepts_canonical_e164() -> None:
    assert require_e164_phone_number("+4795230903") == "+4795230903"


def test_require_e164_phone_number_rejects_non_e164_input() -> None:
    with pytest.raises(ValueError):
        require_e164_phone_number("95230903")


def test_normalize_required_phone_number_accepts_local_norwegian_number() -> None:
    assert normalize_required_phone_number("95230903") == "+4795230903"


def test_normalize_required_phone_number_accepts_explicit_norwegian_fallback() -> None:
    assert (
        normalize_required_phone_number("+47 000 00 000")
        == NORWEGIAN_PHONE_FALLBACK
    )


def test_normalize_required_phone_number_rejects_invalid_phone() -> None:
    with pytest.raises(ValueError, match="gyldig telefonnummer"):
        normalize_required_phone_number("123")
