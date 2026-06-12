"""Development-only photo storage backed by a local directory.

Implements the parts of the ``StorageService`` surface the app uses
(upload, download, remove, close) so the photo pipeline and the media
proxy work against the local harness without Azure credentials.
Selected by ``app/runtime.py`` only in development when Azure is not
configured.
"""

from __future__ import annotations

from pathlib import Path

from app.errors import NotConfiguredError


class LocalDirectoryStorage:
    def __init__(self, root: str | Path = ".devdata/photos") -> None:
        self.root = Path(root)

    def upload_photo(
        self, path: str, content: bytes, content_type: str | None = None
    ) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def download_photo(self, path: str) -> bytes:
        target = self._resolve(path)
        if not target.is_file():
            raise NotConfiguredError(f"Photo {path} is not present locally.")
        return target.read_bytes()

    def remove_photo(self, path: str) -> None:
        target = self._resolve(path)
        target.unlink(missing_ok=True)

    def close(self) -> None:
        return None

    def _resolve(self, path: str) -> Path:
        # Photos are flat hash-named files; refuse anything path-like.
        name = Path(path).name
        if name != path:
            raise NotConfiguredError(f"Invalid photo path: {path!r}")
        return self.root / name
