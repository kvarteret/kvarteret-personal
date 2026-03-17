from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings, get_settings


class MediaTokenService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._serializer = URLSafeTimedSerializer(settings.app_secret_key, salt="kvarteret-media")

    def sign_media_token(self, *, kind: str, path: str) -> str:
        return self._serializer.dumps({"kind": kind, "path": path})

    def verify_media_token(self, *, token: str, kind: str, path: str, max_age: int = 900) -> bool:
        try:
            payload = self._serializer.loads(token, max_age=max_age)
        except (BadSignature, SignatureExpired):
            return False
        return payload == {"kind": kind, "path": path}

    def build_photo_media_url(self, path: str) -> str:
        return self._build_media_url(kind="photo", base_path=f"/media/photos/{path}", path=path)

    def build_document_media_url(self, path: str) -> str:
        return self._build_media_url(kind="document", base_path=f"/media/documents/{path}", path=path)

    def _build_media_url(self, *, kind: str, base_path: str, path: str) -> str:
        token = self.sign_media_token(kind=kind, path=path)
        prefix = self.settings.app_public_base_url.rstrip("/") if self.settings.app_public_base_url else ""
        return f"{prefix}{base_path}?token={token}"


def sign_media_token(*, kind: str, path: str) -> str:
    return MediaTokenService(get_settings()).sign_media_token(kind=kind, path=path)


def verify_media_token(*, token: str, kind: str, path: str, max_age: int = 900) -> bool:
    return MediaTokenService(get_settings()).verify_media_token(token=token, kind=kind, path=path, max_age=max_age)


def build_photo_media_url(path: str) -> str:
    return MediaTokenService(get_settings()).build_photo_media_url(path)


def build_document_media_url(path: str) -> str:
    return MediaTokenService(get_settings()).build_document_media_url(path)
