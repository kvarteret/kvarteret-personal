from __future__ import annotations

from itsdangerous import URLSafeSerializer

from app.config import Settings, get_settings


class SessionCookieSigner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._serializer = URLSafeSerializer(settings.app_secret_key, salt="kvarteret-session")

    def sign_session_id(self, session_id: str) -> str:
        return self._serializer.dumps(session_id)

    def unsign_session_id(self, value: str) -> str:
        return self._serializer.loads(value)


def sign_session_id(session_id: str) -> str:
    return SessionCookieSigner(get_settings()).sign_session_id(session_id)


def unsign_session_id(value: str) -> str:
    return SessionCookieSigner(get_settings()).unsign_session_id(value)
