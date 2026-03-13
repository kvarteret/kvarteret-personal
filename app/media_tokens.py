from __future__ import annotations

from functools import lru_cache

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings


@lru_cache(maxsize=1)
def get_media_token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().app_secret_key, salt="kvarteret-media")


def sign_media_token(*, kind: str, path: str) -> str:
    return get_media_token_serializer().dumps({"kind": kind, "path": path})


def verify_media_token(*, token: str, kind: str, path: str, max_age: int = 900) -> bool:
    try:
        payload = get_media_token_serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return False
    return payload == {"kind": kind, "path": path}


def build_photo_media_url(path: str) -> str:
    token = sign_media_token(kind="photo", path=path)
    settings = get_settings()
    prefix = settings.app_public_base_url.rstrip("/") if settings.app_public_base_url else ""
    return f"{prefix}/media/photos/{path}?token={token}"


def build_document_media_url(path: str) -> str:
    token = sign_media_token(kind="document", path=path)
    settings = get_settings()
    prefix = settings.app_public_base_url.rstrip("/") if settings.app_public_base_url else ""
    return f"{prefix}/media/documents/{path}?token={token}"
