from __future__ import annotations

import time

from itsdangerous import (
    BadSignature,
    SignatureExpired,
    TimestampSigner,
    URLSafeTimedSerializer,
)

from app.config import Settings, get_settings

# Tokens are stamped with the start of the current window instead of the
# current second, so every render inside a window produces the same URL and the
# browser can cache the image. Verification floors "now" the same way, so a
# max age of one window keeps a token valid until the end of the next window:
# between one and two windows after it was issued.
MEDIA_TOKEN_WINDOW_SECONDS = 3600
MEDIA_TOKEN_MAX_AGE_SECONDS = MEDIA_TOKEN_WINDOW_SECONDS


class _WindowedTimestampSigner(TimestampSigner):
    def get_timestamp(self) -> int:
        now = int(time.time())
        return now - now % MEDIA_TOKEN_WINDOW_SECONDS


class MediaTokenService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._serializer = URLSafeTimedSerializer(
            settings.app_secret_key,
            salt="kvarteret-media",
            signer=_WindowedTimestampSigner,
        )

    def sign_media_token(self, *, kind: str, path: str) -> str:
        return self._serializer.dumps({"kind": kind, "path": path})

    def verify_media_token(
        self, *, token: str, kind: str, path: str, max_age: int = MEDIA_TOKEN_MAX_AGE_SECONDS
    ) -> bool:
        try:
            payload = self._serializer.loads(token, max_age=max_age)
        except (BadSignature, SignatureExpired):
            return False
        return payload == {"kind": kind, "path": path}

    def build_photo_media_url(self, path: str, *, relative: bool = False) -> str:
        return self._build_media_url(
            kind="photo", base_path=f"/media/photos/{path}", path=path, relative=relative
        )

    def _build_media_url(self, *, kind: str, base_path: str, path: str, relative: bool = False) -> str:
        token = self.sign_media_token(kind=kind, path=path)
        prefix = (
            self.settings.app_public_base_url.rstrip("/")
            if self.settings.app_public_base_url and not relative
            else ""
        )
        return f"{prefix}{base_path}?token={token}"


def sign_media_token(*, kind: str, path: str) -> str:
    return MediaTokenService(get_settings()).sign_media_token(kind=kind, path=path)


def verify_media_token(
    *, token: str, kind: str, path: str, max_age: int = MEDIA_TOKEN_MAX_AGE_SECONDS
) -> bool:
    return MediaTokenService(get_settings()).verify_media_token(
        token=token, kind=kind, path=path, max_age=max_age
    )


def build_photo_media_url(path: str) -> str:
    return MediaTokenService(get_settings()).build_photo_media_url(path)
