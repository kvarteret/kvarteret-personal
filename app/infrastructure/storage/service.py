from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)

from app.config import Settings, get_settings
from app.errors import NotConfiguredError


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


# Personnel photos are stored in Azure Blob Storage. Supabase remains the app's
# database/auth provider, but not a media storage backend.
class StorageService:
    def __init__(
        self,
        settings: Settings,
        blob_service_client: BlobServiceClient
        | BlobServiceClientProtocol
        | None = None,
    ) -> None:
        self.settings = settings
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
        if self._blob_service_client is None:
            raise NotConfiguredError("Media storage is not configured.")

    def create_photo_signed_url(self, path: str, expires_in: int = 60) -> str:
        return self._create_azure_photo_signed_url(path, expires_in)

    def download_photo(self, path: str) -> bytes:
        return self._download_azure_photo(path)

    def upload_photo(
        self, path: str, content: bytes, content_type: str | None = None
    ) -> None:
        self._upload_azure_photo(path, content, content_type)

    def remove_photo(self, path: str) -> None:
        self._remove_azure_photo(path)

    def close(self) -> None:
        if self._blob_service_client is not None:
            close = getattr(self._blob_service_client, "close", None)
            if callable(close):
                close()

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
