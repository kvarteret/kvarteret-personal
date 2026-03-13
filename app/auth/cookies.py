from __future__ import annotations

from functools import lru_cache

from itsdangerous import URLSafeSerializer

from app.config import get_settings


@lru_cache(maxsize=1)
def get_session_cookie_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().app_secret_key, salt="kvarteret-session")


def sign_session_id(session_id: str) -> str:
    return get_session_cookie_serializer().dumps(session_id)


def unsign_session_id(value: str) -> str:
    return get_session_cookie_serializer().loads(value)

