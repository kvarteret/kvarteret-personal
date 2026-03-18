from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

_SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SPOTIFY_CURRENTLY_PLAYING_URL = "https://api.spotify.com/v1/me/player/currently-playing"


@dataclass(frozen=True, slots=True)
class NowPlayingResult:
    state: dict[str, object]
    cache_hit: bool
    cache_stale: bool
    cache_seconds: float


@dataclass(slots=True)
class _CacheEntry:
    state: dict[str, object]
    fetched_at: float


class NowPlayingService:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient(timeout=20.0, follow_redirects=True)
        self._owns_client = client is None
        self._now_fn = now_fn or monotonic
        self._cache_lock = asyncio.Lock()
        self._cache_entry: _CacheEntry | None = None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_state(self) -> NowPlayingResult:
        cache_seconds = self.settings.now_playing_cache_seconds
        stale_grace_seconds = self.settings.now_playing_stale_grace_seconds
        if not self._has_credentials():
            return NowPlayingResult(
                state=self._default_state(authorized=False),
                cache_hit=False,
                cache_stale=False,
                cache_seconds=cache_seconds,
            )

        try:
            return await self._get_state_with_cache(
                cache_seconds=cache_seconds,
                stale_grace_seconds=stale_grace_seconds,
            )
        except Exception:
            logger.exception("Failed to fetch now playing track")
            return NowPlayingResult(
                state=self._default_state(authorized=True),
                cache_hit=False,
                cache_stale=False,
                cache_seconds=cache_seconds,
            )

    async def _get_state_with_cache(self, *, cache_seconds: float, stale_grace_seconds: float) -> NowPlayingResult:
        now = self._now_fn()
        entry = self._cache_entry
        if entry and _cache_age_seconds(now, entry) <= cache_seconds:
            return _result(entry, cache_hit=True, cache_stale=False, cache_seconds=cache_seconds)

        if self._cache_lock.locked():
            if entry and _cache_age_seconds(now, entry) <= cache_seconds + stale_grace_seconds:
                return _result(entry, cache_hit=True, cache_stale=True, cache_seconds=cache_seconds)
            async with self._cache_lock:
                return await self._refresh_locked(
                    cache_seconds=cache_seconds,
                    stale_grace_seconds=stale_grace_seconds,
                )

        async with self._cache_lock:
            return await self._refresh_locked(
                cache_seconds=cache_seconds,
                stale_grace_seconds=stale_grace_seconds,
            )

    async def _refresh_locked(self, *, cache_seconds: float, stale_grace_seconds: float) -> NowPlayingResult:
        now = self._now_fn()
        entry = self._cache_entry
        if entry and _cache_age_seconds(now, entry) <= cache_seconds:
            return _result(entry, cache_hit=True, cache_stale=False, cache_seconds=cache_seconds)

        try:
            fresh_state = await self._fetch_state_uncached()
        except Exception:
            if entry and _cache_age_seconds(now, entry) <= cache_seconds + stale_grace_seconds:
                logger.warning("Serving stale now-playing snapshot after refresh failure")
                return _result(entry, cache_hit=True, cache_stale=True, cache_seconds=cache_seconds)
            raise

        self._cache_entry = _CacheEntry(state=dict(fresh_state), fetched_at=self._now_fn())
        return NowPlayingResult(
            state=dict(fresh_state),
            cache_hit=False,
            cache_stale=False,
            cache_seconds=cache_seconds,
        )

    async def _fetch_state_uncached(self) -> dict[str, object]:
        access_token = await self._refresh_access_token()
        response = await self._client.get(
            _SPOTIFY_CURRENTLY_PLAYING_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        )

        if response.status_code == 204:
            return self._default_state(authorized=True)
        response.raise_for_status()

        payload = response.json()
        item = payload.get("item")
        if not isinstance(item, dict):
            return self._default_state(authorized=True)

        progress_ms = _int_or_none(payload.get("progress_ms"))
        duration_ms = _int_or_none(item.get("duration_ms"))
        progress_percent = None
        if progress_ms is not None and duration_ms and duration_ms > 0:
            progress_percent = round((progress_ms / duration_ms) * 100, 1)

        album = item.get("album") if isinstance(item.get("album"), dict) else {}
        images = album.get("images") if isinstance(album.get("images"), list) else []
        image = None
        if images:
            first_image = images[0]
            if isinstance(first_image, dict):
                image = _str_or_none(first_image.get("url"))

        artists = ", ".join(
            artist_name
            for artist in item.get("artists", [])
            if isinstance(artist, dict) and (artist_name := _str_or_none(artist.get("name")))
        )

        return {
            **self._default_state(authorized=True),
            "hasTrack": True,
            "isPlaybackActive": bool(payload.get("is_playing", False)),
            "name": _str_or_none(item.get("name")),
            "artists": artists or None,
            "album": _str_or_none(album.get("name")),
            "image": image,
            "progressMs": progress_ms,
            "durationMs": duration_ms,
            "progressPercent": progress_percent,
        }

    async def _refresh_access_token(self) -> str:
        response = await self._client.post(
            _SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.settings.spotify_refresh_token or "",
            },
            auth=(self.settings.spotify_client_id or "", self.settings.spotify_client_secret or ""),
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        access_token = _str_or_none(payload.get("access_token"))
        if not access_token:
            msg = "Spotify token refresh response lacked access_token."
            raise RuntimeError(msg)
        return access_token

    def _has_credentials(self) -> bool:
        return bool(
            self.settings.spotify_client_id
            and self.settings.spotify_client_secret
            and self.settings.spotify_refresh_token
        )

    def _default_state(self, *, authorized: bool) -> dict[str, object]:
        return {
            "authorized": authorized,
            "hasTrack": False,
            "isPlaybackActive": False,
            "name": None,
            "artists": None,
            "album": None,
            "image": None,
            "progressMs": None,
            "durationMs": None,
            "progressPercent": None,
            "connectUrl": self._connect_url(),
        }

    def _connect_url(self) -> str:
        public_base_url = (self.settings.app_public_base_url or "").strip().rstrip("/")
        if public_base_url:
            return f"{public_base_url}/login"
        return ""


def _cache_age_seconds(now: float, entry: _CacheEntry) -> float:
    return max(0.0, now - entry.fetched_at)


def _result(entry: _CacheEntry, *, cache_hit: bool, cache_stale: bool, cache_seconds: float) -> NowPlayingResult:
    return NowPlayingResult(
        state=dict(entry.state),
        cache_hit=cache_hit,
        cache_stale=cache_stale,
        cache_seconds=cache_seconds,
    )


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None
