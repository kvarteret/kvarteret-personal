"""Entry point from Personal to the website's arrangement statistics.

The website reads the shared Personal session cookie and asks
``/api/v1/me/statistikk-tilgang`` what the viewer may see, so this route only
makes sure the viewer is logged in before sending them there.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import RedirectResponse

from app.dependencies import get_current_user, get_settings

router = APIRouter()


@router.get("/statistikk")
async def event_statistics(
    current_user=Depends(get_current_user),
    settings=Depends(get_settings),
):
    if current_user is None:
        return RedirectResponse(
            url="/login?next=/statistikk", status_code=status.HTTP_303_SEE_OTHER
        )
    website = settings.website_base_url.rstrip("/")
    return RedirectResponse(
        url=f"{website}/nb/arrangementer/statistikk",
        status_code=status.HTTP_303_SEE_OTHER,
    )
