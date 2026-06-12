from __future__ import annotations

from typing import Protocol

from app.infrastructure.media.photo_processing import ProcessedPhoto


class PhotoProcessorProtocol(Protocol):
    """Validates and re-encodes an uploaded photo.

    The concrete implementation (``photo_processing.process_uploaded_photo``)
    is injected at wiring time in ``app/runtime.py``.
    """

    def __call__(
        self, content: bytes, *, max_upload_bytes: int, max_dimension: int
    ) -> ProcessedPhoto: ...
