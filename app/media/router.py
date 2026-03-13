from __future__ import annotations

import mimetypes
from asyncio import to_thread

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import Response

from app.media_tokens import verify_media_token
from app.services.storage import StorageService

router = APIRouter()


def _get_storage_service(request: Request) -> StorageService:
    storage_service = request.app.state.container.storage_service
    if storage_service is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Media storage is not configured.")
    return storage_service


@router.get("/media/photos/{photo_path:path}")
async def get_photo(request: Request, photo_path: str, token: str = Query(..., min_length=1)) -> Response:
    if not verify_media_token(token=token, kind="photo", path=photo_path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid media token.")
    try:
        content = await to_thread(_get_storage_service(request).download_photo, photo_path)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found.") from exc
    media_type = mimetypes.guess_type(photo_path)[0] or "application/octet-stream"
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "private, max-age=300"})


@router.get("/media/documents/{document_path:path}")
async def get_document(request: Request, document_path: str, token: str = Query(..., min_length=1)) -> Response:
    if not verify_media_token(token=token, kind="document", path=document_path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid media token.")
    try:
        content = await to_thread(_get_storage_service(request).download_document, document_path)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from exc
    media_type = mimetypes.guess_type(document_path)[0] or "application/octet-stream"
    filename = document_path.rsplit("/", 1)[-1]
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )
