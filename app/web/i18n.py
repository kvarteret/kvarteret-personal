from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from gettext import GNUTranslations, NullTranslations, translation
from pathlib import Path

TRANSLATION_DOMAIN = "public_pages"
LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"

PublicTranslations = GNUTranslations | NullTranslations

_DEFAULT_LOCALE = "en"
_current_locale: ContextVar[str] = ContextVar("public_locale", default=_DEFAULT_LOCALE)
_current_translations: ContextVar[PublicTranslations] = ContextVar(
    "public_translations",
    default=NullTranslations(),
)

_PUBLIC_MESSAGE_ID_MAP = {
    "Skriv inn et gyldig telefonnummer.": "Enter a valid phone number.",
    "Profilbilde er påkrevd.": "Profile photo is required.",
}


@lru_cache(maxsize=4)
def get_public_translations(locale: str) -> PublicTranslations:
    return translation(
        TRANSLATION_DOMAIN,
        localedir=str(LOCALES_DIR),
        languages=[locale],
        fallback=True,
    )


def resolve_public_locale(accept_language_header: str | None) -> str:
    top_language = _top_preferred_language(accept_language_header)
    if top_language is None:
        return _DEFAULT_LOCALE
    if top_language.startswith(("nb", "nn", "no")):
        return "nb"
    return _DEFAULT_LOCALE


def translate_public(locale: str, message: str, **variables: object) -> str:
    message_id = _PUBLIC_MESSAGE_ID_MAP.get(message, message)
    translated = get_public_translations(locale).gettext(message_id)
    return translated % variables if variables else translated


@contextmanager
def activate_public_locale(locale: str) -> Iterator[None]:
    translations = get_public_translations(locale)
    locale_token = _current_locale.set(locale)
    translations_token = _current_translations.set(translations)
    try:
        yield
    finally:
        _current_locale.reset(locale_token)
        _current_translations.reset(translations_token)


def get_template_gettext(message: str, **variables: object) -> str:
    translated = _current_translations.get().gettext(message)
    return translated % variables if variables else translated


def get_template_ngettext(
    singular: str, plural: str, count: int, **variables: object
) -> str:
    translated = _current_translations.get().ngettext(singular, plural, count)
    payload = {"count": count, **variables}
    return translated % payload if payload else translated


def apply_locale_vary_header(response) -> None:
    existing = response.headers.get("Vary", "")
    merged = {value.strip() for value in existing.split(",") if value.strip()}
    merged.add("Accept-Language")
    response.headers["Vary"] = ", ".join(sorted(merged))


def current_public_locale() -> str:
    return _current_locale.get()


def _top_preferred_language(accept_language_header: str | None) -> str | None:
    if accept_language_header is None or not accept_language_header.strip():
        return None

    ranked_languages: list[tuple[float, int, str]] = []
    for index, item in enumerate(accept_language_header.split(",")):
        candidate = item.strip()
        if not candidate:
            continue
        language, *parameters = [part.strip() for part in candidate.split(";")]
        quality = 1.0
        for parameter in parameters:
            if not parameter.startswith("q="):
                continue
            try:
                quality = float(parameter[2:])
            except ValueError:
                quality = 0.0
        ranked_languages.append((quality, -index, language.lower()))

    if not ranked_languages:
        return None

    ranked_languages.sort(reverse=True)
    return ranked_languages[0][2]
