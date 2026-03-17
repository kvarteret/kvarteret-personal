from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.config import Settings, get_settings
from app.errors import NotConfiguredError


class StorageHttpClientProtocol(Protocol):
    def request(self, method: str, url: str, **kwargs) -> httpx.Response: ...
    def close(self) -> None: ...


class StorageService:
    def __init__(self, settings: Settings, client: StorageHttpClientProtocol | None = None) -> None:
        if not settings.supabase_url or not settings.supabase_secret_key:
            raise NotConfiguredError("Supabase credentials are required for storage integration.")
        self.settings = settings
        self._base_url = f"{settings.supabase_url.rstrip('/')}/storage/v1"
        self._headers = {
            "apikey": settings.supabase_secret_key,
            "Authorization": f"Bearer {settings.supabase_secret_key}",
        }
        self._client = client or httpx.Client(timeout=20.0, follow_redirects=True)

    def create_photo_signed_url(self, path: str, expires_in: int = 60) -> str:
        return self._create_signed_url(self.settings.photo_bucket, path, expires_in)

    def create_document_signed_url(self, path: str, expires_in: int = 300) -> str:
        return self._create_signed_url(self.settings.document_bucket, path, expires_in)

    def download_photo(self, path: str) -> bytes:
        return self._download(self.settings.photo_bucket, path)

    def download_document(self, path: str) -> bytes:
        return self._download(self.settings.document_bucket, path)

    def upload_photo(self, path: str, content: bytes, content_type: str | None = None) -> None:
        self._upload(self.settings.photo_bucket, path, content, content_type)

    def upload_document(self, path: str, content: bytes, content_type: str | None = None) -> None:
        self._upload(self.settings.document_bucket, path, content, content_type)

    def remove_photo(self, path: str) -> None:
        self._remove(self.settings.photo_bucket, path)

    def remove_document(self, path: str) -> None:
        self._remove(self.settings.document_bucket, path)

    def close(self) -> None:
        self._client.close()

    def _create_signed_url(self, bucket: str, path: str, expires_in: int) -> str:
        response = self._request(
            "POST",
            f"object/sign/{bucket}/{path.lstrip('/')}",
            json={"expiresIn": str(expires_in)},
        )
        return self._extract_signed_url(response.json())

    def _download(self, bucket: str, path: str) -> bytes:
        response = self._request("GET", f"object/{bucket}/{path.lstrip('/')}")
        return response.content

    def _upload(self, bucket: str, path: str, content: bytes, content_type: str | None) -> None:
        filename = Path(path).name
        headers = {**self._headers, "x-upsert": "true"}
        files = {
            "file": (
                filename,
                content,
                content_type or "application/octet-stream",
            )
        }
        self._request(
            "POST",
            f"object/{bucket}/{path.lstrip('/')}",
            headers=headers,
            files=files,
        )

    def _remove(self, bucket: str, path: str) -> None:
        self._request("DELETE", f"object/{bucket}", json={"prefixes": [path]})

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> httpx.Response:
        response = self._client.request(
            method,
            f"{self._base_url}/{path}",
            headers=headers or self._headers,
            json=json,
            files=files,
        )
        response.raise_for_status()
        return response

    def _extract_signed_url(self, result: dict[str, Any]) -> str:
        data = result.get("signedURL") or result.get("signedUrl")
        if data:
            return self._coerce_signed_url(data)
        if isinstance(result.get("data"), dict):
            nested = result["data"].get("signedURL") or result["data"].get("signedUrl")
            if nested:
                return self._coerce_signed_url(nested)
        raise NotConfiguredError("Supabase did not return a signed URL.")

    def _coerce_signed_url(self, value: str) -> str:
        if value.startswith("http://") or value.startswith("https://"):
            return value
        if value.startswith("/"):
            return f"{self._base_url.rstrip('/')}{value}"
        return f"{self._base_url.rstrip('/')}/{value.lstrip('/')}"


@lru_cache(maxsize=1)
def get_storage_service() -> StorageService:
    return StorageService(get_settings())


def create_photo_signed_url(path: str, expires_in: int = 60) -> str:
    return get_storage_service().create_photo_signed_url(path, expires_in)


def create_document_signed_url(path: str, expires_in: int = 300) -> str:
    return get_storage_service().create_document_signed_url(path, expires_in)
