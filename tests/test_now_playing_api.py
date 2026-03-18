from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_now_playing_service
from app.main import create_app
from app.services.now_playing import NowPlayingResult, NowPlayingService
from app.config import Settings


class FakeNowPlayingService:
    async def get_state(self) -> NowPlayingResult:
        return NowPlayingResult(
            state={
                "authorized": True,
                "hasTrack": True,
                "isPlaybackActive": True,
                "name": "Track",
                "artists": "Artist One, Artist Two",
                "album": "Album",
                "image": "https://example.com/cover.jpg",
                "progressMs": 1500,
                "durationMs": 3000,
                "progressPercent": 50.0,
                "connectUrl": "https://personal.kvarteret.no/login",
            },
            cache_hit=True,
            cache_stale=False,
            cache_seconds=10.0,
        )


def test_now_playing_api_returns_public_json_with_cache_headers() -> None:
    app = create_app()
    app.dependency_overrides[get_now_playing_service] = lambda: FakeNowPlayingService()
    client = TestClient(app)

    response = client.get("/api/now-playing")

    assert response.status_code == 200
    assert response.json()["hasTrack"] is True
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert response.headers["X-Now-Playing-Cache-Seconds"] == "10.0"
    assert response.headers["X-Now-Playing-Cache-Hit"] == "1"
    assert response.headers["X-Now-Playing-Cache-Stale"] == "0"


@pytest.mark.asyncio
async def test_now_playing_service_fetches_current_track_from_spotify() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url)))
        if str(request.url) == "https://accounts.spotify.com/api/token":
            return httpx.Response(200, json={"access_token": "spotify-access-token"})
        if str(request.url) == "https://api.spotify.com/v1/me/player/currently-playing":
            return httpx.Response(
                200,
                json={
                    "is_playing": True,
                    "progress_ms": 1500,
                    "item": {
                        "name": "Track",
                        "duration_ms": 3000,
                        "artists": [{"name": "Artist One"}, {"name": "Artist Two"}],
                        "album": {
                            "name": "Album",
                            "images": [{"url": "https://example.com/cover.jpg"}],
                        },
                    },
                },
            )
        raise AssertionError(f"Unexpected request to {request.url}")

    service = NowPlayingService(
        Settings(
            app_public_base_url="https://personal.kvarteret.no",
            spotify_client_id="spotify-client-id",
            spotify_client_secret="spotify-client-secret",
            spotify_refresh_token="spotify-refresh-token",
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await service.get_state()
    await service.aclose()

    assert requests == [
        ("POST", "https://accounts.spotify.com/api/token"),
        ("GET", "https://api.spotify.com/v1/me/player/currently-playing"),
    ]
    assert result.state == {
        "authorized": True,
        "hasTrack": True,
        "isPlaybackActive": True,
        "name": "Track",
        "artists": "Artist One, Artist Two",
        "album": "Album",
        "image": "https://example.com/cover.jpg",
        "progressMs": 1500,
        "durationMs": 3000,
        "progressPercent": 50.0,
        "connectUrl": "https://personal.kvarteret.no/login",
    }


@pytest.mark.asyncio
async def test_now_playing_service_returns_unconfigured_state_without_spotify_credentials() -> None:
    service = NowPlayingService(Settings())

    result = await service.get_state()
    await service.aclose()

    assert result.state == {
        "authorized": False,
        "hasTrack": False,
        "isPlaybackActive": False,
        "name": None,
        "artists": None,
        "album": None,
        "image": None,
        "progressMs": None,
        "durationMs": None,
        "progressPercent": None,
        "connectUrl": "",
    }
