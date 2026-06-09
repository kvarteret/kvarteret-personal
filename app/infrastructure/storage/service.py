from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import httpx
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)

from app.config import Settings, get_settings
from app.errors import NotConfiguredError


class StorageHttpClientProtocol(Protocol):
    def request(self, method: str, url: str, **kwargs) -> httpx.Response: ...
    def close(self) -> None: ...


class BlobDownloadStreamProtocol(Protocol):
    def readall(self) -> bytes: ...


class BlobClientProtocol(Protocol):
    url: str

    def download_blob(self) -> BlobDownloadStreamProtocol: ...
    def upload_blob(
        self, content: bytes, *, overwrite: bool, content_settings: ContentSettings
    ) -> None: ...
    def delete_blob(self) -> None: ...


class BlobContainerClientProtocol(Protocol):
    def create_container(self) -> None: ...
    def get_blob_client(self, blob_name: str) -> BlobClientProtocol: ...


class BlobServiceClientProtocol(Protocol):
    def get_container_client(
        self, container_name: str
    ) -> BlobContainerClientProtocol: ...


# This adapter deliberately hides a split storage setup: photos can stay on Azure
# for legacy compatibility, while private documents continue to use Supabase storage APIs.
class StorageService:
    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | StorageHttpClientProtocol | None = None,
        blob_service_client: BlobServiceClient
        | BlobServiceClientProtocol
        | None = None,
    ) -> None:
        self.settings = settings
        if _has_supabase_documents(settings):
            assert settings.supabase_url is not None
            assert settings.supabase_secret_key is not None
            self._base_url = f"{settings.supabase_url.rstrip('/')}/storage/v1"
            self._headers: dict[str, str] = {
                "apikey": settings.supabase_secret_key,
                "Authorization": f"Bearer {settings.supabase_secret_key}",
            }
        else:
            self._base_url = None
            self._headers = {}
        self._client = client or (
            httpx.Client(timeout=20.0, follow_redirects=True)
            if _has_supabase_documents(settings)
            else None
        )
        self._blob_service_client: (
            BlobServiceClient | BlobServiceClientProtocol | None
        ) = blob_service_client or _build_blob_service_client(settings)
        self._azure_account_name = (
            settings.azure_blob_account_name
            or _parse_connection_string_value(
                settings.azure_blob_connection_string,
                "AccountName",
            )
        )
        self._azure_account_key = (
            settings.azure_blob_account_key
            or _parse_connection_string_value(
                settings.azure_blob_connection_string,
                "AccountKey",
            )
        )
        if self._client is None and self._blob_service_client is None:
            raise NotConfiguredError("Media storage is not configured.")

    def create_photo_signed_url(self, path: str, expires_in: int = 60) -> str:
        if self._blob_service_client is not None:
            return self._create_azure_photo_signed_url(path, expires_in)
        return self._create_signed_url(self.settings.photo_bucket, path, expires_in)

    def create_document_signed_url(self, path: str, expires_in: int = 300) -> str:
        self._require_supabase_documents()
        return self._create_signed_url(self.settings.document_bucket, path, expires_in)

    def download_photo(self, path: str) -> bytes:
        if self._blob_service_client is not None:
            return self._download_azure_photo(path)
        return self._download(self.settings.photo_bucket, path)

    def download_document(self, path: str) -> bytes:
        self._require_supabase_documents()
        return self._download(self.settings.document_bucket, path)

    def upload_photo(
        self, path: str, content: bytes, content_type: str | None = None
    ) -> None:
        if self._blob_service_client is not None:
            self._upload_azure_photo(path, content, content_type)
            return
        self._upload(self.settings.photo_bucket, path, content, content_type)

    def upload_document(
        self, path: str, content: bytes, content_type: str | None = None
    ) -> None:
        self._require_supabase_documents()
        self._upload(self.settings.document_bucket, path, content, content_type)

    def remove_photo(self, path: str) -> None:
        if self._blob_service_client is not None:
            self._remove_azure_photo(path)
            return
        self._remove(self.settings.photo_bucket, path)

    def remove_document(self, path: str) -> None:
        self._require_supabase_documents()
        self._remove(self.settings.document_bucket, path)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
        if self._blob_service_client is not None:
            close = getattr(self._blob_service_client, "close", None)
            if callable(close):
                close()

    def list_buckets(self) -> list[dict[str, Any]]:
        self._require_supabase_documents()
        response = self._request("GET", "bucket")
        data = response.json()
        if not isinstance(data, list):
            raise NotConfiguredError("Supabase did not return a bucket list.")
        return data

    def empty_bucket(self, bucket: str) -> str:
        self._require_supabase_documents()
        response = self._request("POST", f"bucket/{bucket}/empty")
        data = response.json()
        if isinstance(data, dict):
            message = data.get("message")
            if isinstance(message, str) and message:
                return message
        return "Bucket empty request accepted."

    def _create_azure_photo_signed_url(self, path: str, expires_in: int) -> str:
        blob_path = path.lstrip("/")
        account_name = self._azure_account_name
        account_key = self._azure_account_key
        if not account_name or not account_key:
            raise NotConfiguredError(
                "Azure Blob account credentials are required for photo SAS generation."
            )
        blob_client = self._get_photo_container_client().get_blob_client(blob_path)
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=self.settings.azure_photo_container,
            blob_name=blob_path,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            start=datetime.now(UTC),
            expiry=datetime.now(UTC) + timedelta(seconds=expires_in),
        )
        return f"{blob_client.url}?{sas_token}"

    def _download_azure_photo(self, path: str) -> bytes:
        blob_client = self._get_photo_container_client().get_blob_client(
            path.lstrip("/")
        )
        return blob_client.download_blob().readall()

    def _upload_azure_photo(
        self, path: str, content: bytes, content_type: str | None
    ) -> None:
        container_client = self._get_photo_container_client()
        try:
            container_client.create_container()
        except ResourceExistsError:
            pass
        blob_client = container_client.get_blob_client(path.lstrip("/"))
        blob_client.upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(
                content_type=content_type or "application/octet-stream"
            ),
        )

    def _remove_azure_photo(self, path: str) -> None:
        blob_client = self._get_photo_container_client().get_blob_client(
            path.lstrip("/")
        )
        try:
            blob_client.delete_blob()
        except ResourceNotFoundError:
            return

    def _get_photo_container_client(self):
        if self._blob_service_client is None:
            raise NotConfiguredError(
                "Azure Blob credentials are required for photo storage."
            )
        return self._blob_service_client.get_container_client(
            self.settings.azure_photo_container
        )

    def _require_supabase_documents(self) -> None:
        if self._client is None or self._base_url is None:
            raise NotConfiguredError(
                "Supabase credentials are required for document storage."
            )

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

    def _upload(
        self, bucket: str, path: str, content: bytes, content_type: str | None
    ) -> None:
        filename = Path(path).name
        headers: dict[str, str] = {**self._headers, "x-upsert": "true"}
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
        if self._client is None or self._base_url is None:
            raise NotConfiguredError(
                "Supabase credentials are required for document storage."
            )
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
        # Supabase has returned both signedURL and signedUrl payloads, so normalize
        # the shape here before the rest of the app has to care about provider quirks.
        data = result.get("signedURL") or result.get("signedUrl")
        if data:
            return self._coerce_signed_url(data)
        if isinstance(result.get("data"), dict):
            nested = result["data"].get("signedURL") or result["data"].get("signedUrl")
            if nested:
                return self._coerce_signed_url(nested)
        raise NotConfiguredError("Supabase did not return a signed URL.")

    def _coerce_signed_url(self, value: str) -> str:
        if value.startswith(("http://", "https://")):
            return value
        if value.startswith("/"):
            assert self._base_url is not None
            return f"{self._base_url.rstrip('/')}{value}"
        assert self._base_url is not None
        return f"{self._base_url.rstrip('/')}/{value.lstrip('/')}"


def _has_supabase_documents(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_secret_key)


def _build_blob_service_client(settings: Settings) -> BlobServiceClient | None:
    if not settings.azure_blob_connection_string:
        return None
    return BlobServiceClient.from_connection_string(
        settings.azure_blob_connection_string
    )


def _parse_connection_string_value(
    connection_string: str | None, key: str
) -> str | None:
    if not connection_string:
        return None
    prefix = f"{key}="
    for segment in connection_string.split(";"):
        item = segment.strip()
        if item.startswith(prefix):
            return item[len(prefix) :] or None
    return None


def create_photo_signed_url(path: str, expires_in: int = 60) -> str:
    return StorageService(get_settings()).create_photo_signed_url(path, expires_in)


def create_document_signed_url(path: str, expires_in: int = 300) -> str:
    return StorageService(get_settings()).create_document_signed_url(path, expires_in)
