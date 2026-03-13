from __future__ import annotations

from functools import lru_cache
from typing import Any, Protocol

from supabase import Client, create_client

from app.config import Settings, get_settings
from app.errors import NotConfiguredError


class SignedUrlBucket(Protocol):
    def create_signed_url(self, path: str, expires_in: int) -> dict | str:
        ...

    def download(self, path: str) -> bytes:
        ...

    def upload(self, path: str, file: bytes, file_options: dict[str, Any] | None = None) -> Any:
        ...

    def remove(self, paths: list[str]) -> Any:
        ...


class StorageCapableClient(Protocol):
    @property
    def storage(self): ...


def create_supabase_client(settings: Settings) -> Client:
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise NotConfiguredError("Supabase credentials are required for storage integration.")
    return create_client(settings.supabase_url, settings.supabase_secret_key)


class StorageService:
    def __init__(self, settings: Settings, client: StorageCapableClient | None = None) -> None:
        self.settings = settings
        self.client = client or create_supabase_client(settings)

    def create_photo_signed_url(self, path: str, expires_in: int = 60) -> str:
        result = self.client.storage.from_(self.settings.photo_bucket).create_signed_url(path, expires_in)
        return self._extract_signed_url(result)

    def create_document_signed_url(self, path: str, expires_in: int = 300) -> str:
        result = self.client.storage.from_(self.settings.document_bucket).create_signed_url(path, expires_in)
        return self._extract_signed_url(result)

    def download_photo(self, path: str) -> bytes:
        return self.client.storage.from_(self.settings.photo_bucket).download(path)

    def download_document(self, path: str) -> bytes:
        return self.client.storage.from_(self.settings.document_bucket).download(path)

    def upload_photo(self, path: str, content: bytes, content_type: str | None = None) -> None:
        options: dict[str, str] = {"upsert": "true"}
        if content_type:
            options["content-type"] = content_type
        self.client.storage.from_(self.settings.photo_bucket).upload(path, content, file_options=options)

    def upload_document(self, path: str, content: bytes, content_type: str | None = None) -> None:
        options: dict[str, str] = {"upsert": "true"}
        if content_type:
            options["content-type"] = content_type
        self.client.storage.from_(self.settings.document_bucket).upload(path, content, file_options=options)

    def remove_photo(self, path: str) -> None:
        self.client.storage.from_(self.settings.photo_bucket).remove([path])

    def remove_document(self, path: str) -> None:
        self.client.storage.from_(self.settings.document_bucket).remove([path])

    @staticmethod
    def _extract_signed_url(result: dict | str) -> str:
        if isinstance(result, str):
            return result
        data = result.get("signedURL") or result.get("signedUrl")
        if data:
            return data
        if isinstance(result.get("data"), dict):
            nested = result["data"].get("signedURL") or result["data"].get("signedUrl")
            if nested:
                return nested
        raise NotConfiguredError("Supabase did not return a signed URL.")


@lru_cache(maxsize=1)
def get_storage_service() -> StorageService:
    return StorageService(get_settings())


def create_photo_signed_url(path: str, expires_in: int = 60) -> str:
    return get_storage_service().create_photo_signed_url(path, expires_in)


def create_document_signed_url(path: str, expires_in: int = 300) -> str:
    return get_storage_service().create_document_signed_url(path, expires_in)
