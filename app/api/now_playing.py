from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.dependencies import get_now_playing_service
from app.domain.spotify.now_playing import NowPlayingResult, NowPlayingService


class NowPlayingStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorized: bool
    hasTrack: bool
    isPlaybackActive: bool
    name: str | None = None
    artists: str | None = None
    album: str | None = None
    image: str | None = None
    progressMs: int | None = None
    durationMs: int | None = None
    progressPercent: float | None = None
    connectUrl: str


router = APIRouter()


@router.get(
    "/now-playing",
    response_model=NowPlayingStateResponse,
    operation_id="getNowPlaying",
)
async def get_now_playing(
    service: NowPlayingService = Depends(get_now_playing_service),
) -> JSONResponse:
    result = await service.get_state()
    return JSONResponse(
        content=result.state,
        headers=_cache_headers(result),
    )


def _cache_headers(result: NowPlayingResult) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Now-Playing-Cache-Seconds": str(result.cache_seconds),
        "X-Now-Playing-Cache-Hit": "1" if result.cache_hit else "0",
        "X-Now-Playing-Cache-Stale": "1" if result.cache_stale else "0",
    }
