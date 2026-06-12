from __future__ import annotations

from typing import Protocol


class StorageProtocol(Protocol):
    """Photo storage surface the rest of the app depends on.

    Concrete adapters (Azure ``StorageService``, ``LocalDirectoryStorage``)
    are selected and injected at wiring time in ``app/runtime.py``.
    """

    def upload_photo(
        self, path: str, content: bytes, content_type: str | None = None
    ) -> None: ...
    def download_photo(self, path: str) -> bytes: ...
    def remove_photo(self, path: str) -> None: ...
    def close(self) -> None: ...
