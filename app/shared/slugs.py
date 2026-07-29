"""Stable URL-safe identifiers shared across domain modules."""

from __future__ import annotations

import re
import unicodedata

_NORWEGIAN_TRANSLITERATION = str.maketrans(
    {
        "æ": "ae",
        "ø": "o",
        "å": "a",
        "Æ": "Ae",
        "Ø": "O",
        "Å": "A",
    }
)


def slugify(value: str) -> str:
    """Return a lowercase ASCII slug suitable for cross-system identifiers."""

    transliterated = value.translate(_NORWEGIAN_TRANSLITERATION)
    ascii_value = (
        unicodedata.normalize("NFKD", transliterated)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
