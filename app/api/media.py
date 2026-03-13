from __future__ import annotations

import mimetypes
from asyncio import to_thread

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from app.media_tokens import verify_media_token
from app.services.storage import get_storage_service

router = APIRouter()


@router.get("/media/photos/{photo_path:path}")
async def get_photo(photo_path: str, token: str = Query(..., min_length=1)) -> Response:
    if not verify_media_token(token=token, kind="photo", path=photo_path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid media token.")
    try:
        content = await to_thread(get_storage_service().download_photo, photo_path)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found.")
    media_type = mimetypes.guess_type(photo_path)[0] or "application/octet-stream"
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "private, max-age=300"})


@router.get("/media/documents/{document_path:path}")
async def get_document(document_path: str, token: str = Query(..., min_length=1)) -> Response:
    if not verify_media_token(token=token, kind="document", path=document_path):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid media token.")
    try:
        content = await to_thread(get_storage_service().download_document, document_path)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
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
