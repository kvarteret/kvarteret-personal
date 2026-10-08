from app.config import Settings
from app.media_tokens import (
    MEDIA_TOKEN_WINDOW_SECONDS,
    MediaTokenService,
)


def _service() -> MediaTokenService:
    return MediaTokenService(Settings(app_secret_key="test-secret"))


def test_photo_urls_are_stable_within_a_token_window(monkeypatch):
    window_start = 1_800_000_000 - 1_800_000_000 % MEDIA_TOKEN_WINDOW_SECONDS
    service = _service()

    monkeypatch.setattr("time.time", lambda: window_start + 5)
    first = service.build_photo_media_url("abc.jpg")
    monkeypatch.setattr("time.time", lambda: window_start + MEDIA_TOKEN_WINDOW_SECONDS - 1)
    second = service.build_photo_media_url("abc.jpg")
    monkeypatch.setattr("time.time", lambda: window_start + MEDIA_TOKEN_WINDOW_SECONDS)
    next_window = service.build_photo_media_url("abc.jpg")

    assert first == second
    assert next_window != first


def test_photo_tokens_stay_valid_until_the_end_of_the_next_window(monkeypatch):
    window_start = 1_800_000_000 - 1_800_000_000 % MEDIA_TOKEN_WINDOW_SECONDS
    service = _service()
    monkeypatch.setattr("time.time", lambda: window_start + 10)
    token = service.sign_media_token(kind="photo", path="abc.jpg")

    monkeypatch.setattr(
        "time.time", lambda: window_start + 2 * MEDIA_TOKEN_WINDOW_SECONDS - 1
    )
    assert service.verify_media_token(token=token, kind="photo", path="abc.jpg")
    assert not service.verify_media_token(token=token, kind="photo", path="other.jpg")
    monkeypatch.setattr(
        "time.time", lambda: window_start + 2 * MEDIA_TOKEN_WINDOW_SECONDS
    )
    assert not service.verify_media_token(token=token, kind="photo", path="abc.jpg")
