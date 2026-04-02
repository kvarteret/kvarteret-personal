from __future__ import annotations

from fastapi import UploadFile

from app.infrastructure.media.photo_processing import PhotoUploadTooLargeError


async def read_upload_file_limited(
    upload_file: UploadFile,
    *,
    max_bytes: int,
    chunk_size: int = 256 * 1024,
) -> bytes:
    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = await upload_file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise PhotoUploadTooLargeError(f"Photos must be {max_bytes // (1024 * 1024)} MB or smaller.")
        chunks.append(chunk)

    return b"".join(chunks)
