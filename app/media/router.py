from __future__ import annotations

import logging
import mimetypes
from asyncio import to_thread

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import Response

from app.auth.models import AuthenticatedUser
from app.auth.roles import UserRole
from app.cache import TTLCache
from app.dependencies import (
    get_current_user,
    get_media_token_service,
    get_mobile_card_service,
    get_settings,
    get_volunteers_service,
)
from app.media_tokens import MediaTokenService
from app.domain.mobile_card.service import (
    MobileCardInvalidAccessCodeError,
    MobileCardService,
)
from app.infrastructure.media.photo_processing import (
    ProcessedPhoto,
    render_photo_variant,
)
from app.infrastructure.storage.service import StorageService
from app.domain.volunteers.service import VolunteersService

logger = logging.getLogger(__name__)
_PHOTO_NOT_FOUND = "Photo not found."
router = APIRouter()
SECURE_MEDIA_HEADERS = {
    "Cache-Control": "private, max-age=900",
    "X-Content-Type-Options": "nosniff",
    "Vary": "Accept",
}
AUTHENTICATED_IMAGE_HEADERS = {
    "Cache-Control": "private, max-age=3600",
    "X-Content-Type-Options": "nosniff",
    "Vary": "Accept, Authorization, Cookie",
}
PHOTO_VARIANT_CACHE: TTLCache[tuple[str, int], ProcessedPhoto] = TTLCache(
    ttl_seconds=3600, max_entries=4096
)


def _get_storage_service(request: Request) -> StorageService:
    storage_service = request.app.state.container.storage_service
    if storage_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Media storage is not configured.",
        )
    return storage_service


@router.get("/media/photos/{photo_path:path}")
async def get_photo(
    request: Request,
    photo_path: str,
    token: str = Query(..., min_length=1),
    size: int | None = Query(default=None, ge=32, le=2048),
    settings=Depends(get_settings),
    media_token_service: MediaTokenService = Depends(get_media_token_service),
) -> Response:
    if not media_token_service.verify_media_token(
        token=token, kind="photo", path=photo_path
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid media token."
        )
    try:
        requested_size = _resolve_photo_size(size, settings.photo_default_size)
        photo = await to_thread(
            _load_photo_variant,
            _get_storage_service(request),
            photo_path,
            requested_size,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_PHOTO_NOT_FOUND
        ) from exc
    return _build_photo_response(
        request=request,
        content=photo.content,
        media_type=photo.content_type,
        etag=_photo_etag(photo_path, requested_size),
        headers=SECURE_MEDIA_HEADERS,
    )


@router.get("/images/{volunteer_id}")
async def get_authenticated_photo(
    request: Request,
    volunteer_id: int,
    size: int | None = Query(default=None, ge=32, le=2048),
    authorization: str | None = Header(default=None),
    settings=Depends(get_settings),
    current_user: AuthenticatedUser | None = Depends(get_current_user),
    volunteers_service: VolunteersService = Depends(get_volunteers_service),
    mobile_card_service: MobileCardService = Depends(get_mobile_card_service),
) -> Response:
    authorization_status = await _authorize_photo_request(
        volunteer_id=volunteer_id,
        current_user=current_user,
        authorization=authorization,
        volunteers_service=volunteers_service,
        mobile_card_service=mobile_card_service,
    )
    if authorization_status is not None:
        return authorization_status

    photo_path = await volunteers_service.get_photo_storage_path(volunteer_id)
    if photo_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_PHOTO_NOT_FOUND
        )

    requested_size = _resolve_photo_size(size, settings.photo_default_size)
    try:
        photo = await to_thread(
            _load_photo_variant,
            _get_storage_service(request),
            photo_path,
            requested_size,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_PHOTO_NOT_FOUND
        ) from exc
    return _build_photo_response(
        request=request,
        content=photo.content,
        media_type=photo.content_type,
        etag=_photo_etag(photo_path, requested_size),
        headers=AUTHENTICATED_IMAGE_HEADERS,
    )


def _resolve_photo_size(size: int | None, default_size: int) -> int:
    return size or default_size


def _load_photo_variant(
    storage_service: StorageService, photo_path: str, size: int
) -> ProcessedPhoto:
    cache_key = (photo_path, size)
    cached = PHOTO_VARIANT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    source = storage_service.download_photo(photo_path)
    try:
        rendered = render_photo_variant(source, max_dimension=size)
    except Exception:
        logger.exception(
            "Failed to render photo variant for %s at size=%s; serving original bytes.",
            photo_path,
            size,
        )
        rendered = ProcessedPhoto(
            content=source,
            content_type=mimetypes.guess_type(photo_path)[0]
            or "application/octet-stream",
            extension=photo_path.rsplit(".", 1)[-1].lower()
            if "." in photo_path
            else "",
            width=0,
            height=0,
        )
    PHOTO_VARIANT_CACHE.set(cache_key, rendered)
    return rendered


def _build_photo_response(
    *,
    request: Request,
    content: bytes,
    media_type: str,
    etag: str,
    headers: dict[str, str],
) -> Response:
    response_headers = {
        **headers,
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=response_headers
        )
    return Response(content=content, media_type=media_type, headers=response_headers)


async def _authorize_photo_request(
    *,
    volunteer_id: int,
    current_user: AuthenticatedUser | None,
    authorization: str | None,
    volunteers_service: VolunteersService,
    mobile_card_service: MobileCardService,
) -> Response | None:
    bearer_token = _extract_bearer_token(authorization)
    if bearer_token is not None:
        try:
            card_result = await mobile_card_service.get_current_card(bearer_token)
        except MobileCardInvalidAccessCodeError:
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)
        if card_result.card.person_id != volunteer_id:
            return Response(status_code=status.HTTP_403_FORBIDDEN)
        return None

    if current_user is None:
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    if current_user.role in {UserRole.ADMIN, UserRole.GROUP_ADMIN}:
        return None

    current_volunteer_id = await volunteers_service.find_volunteer_id_by_email(
        current_user.email
    )
    if current_volunteer_id != volunteer_id:
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    return None


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


def _photo_etag(photo_path: str, size: int) -> str:
    identifier = photo_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return f'"photo-{identifier}-{size}"'
