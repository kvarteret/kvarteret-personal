import pytest

from app.config import Settings
from app.errors import NotConfiguredError
from app.infrastructure.storage.service import StorageService


class FakeDownloadStream:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def readall(self) -> bytes:
        return self._content


class FakeBlobClient:
    def __init__(self, *, url: str, download_content: bytes = b"") -> None:
        self.url = url
        self.download_content = download_content
        self.upload_calls: list[dict[str, object]] = []
        self.deleted = False

    def download_blob(self) -> FakeDownloadStream:
        return FakeDownloadStream(self.download_content)

    def upload_blob(self, content: bytes, *, overwrite: bool, content_settings) -> None:
        self.upload_calls.append(
            {
                "content": content,
                "overwrite": overwrite,
                "content_type": content_settings.content_type,
            }
        )

    def delete_blob(self) -> None:
        self.deleted = True


class FakeContainerClient:
    def __init__(self, blob_client: FakeBlobClient) -> None:
        self.blob_client = blob_client
        self.created = False
        self.requested_blob_names: list[str] = []

    def create_container(self) -> None:
        self.created = True

    def get_blob_client(self, blob_name: str) -> FakeBlobClient:
        self.requested_blob_names.append(blob_name)
        return self.blob_client


class FakeBlobServiceClient:
    def __init__(self, container_client: FakeContainerClient) -> None:
        self.container_client = container_client
        self.requested_containers: list[str] = []

    def get_container_client(self, container_name: str) -> FakeContainerClient:
        self.requested_containers.append(container_name)
        return self.container_client


def test_storage_requires_azure_blob_configuration() -> None:
    with pytest.raises(NotConfiguredError, match="Media storage is not configured"):
        StorageService(Settings(azure_blob_connection_string=None))


def test_create_photo_signed_url_uses_azure(monkeypatch) -> None:
    blob_client = FakeBlobClient(
        url="https://personaldatabasen.blob.core.windows.net/images/abc123.jpg"
    )
    service = StorageService(
        Settings(
            azure_blob_connection_string="UseDevelopmentStorage=true",
            azure_blob_account_name="personaldatabasen",
            azure_blob_account_key="secret",
            azure_photo_container="images",
        ),
        blob_service_client=FakeBlobServiceClient(FakeContainerClient(blob_client)),
    )

    monkeypatch.setattr(
        "app.infrastructure.storage.service.generate_blob_sas",
        lambda **kwargs: "sig=1",
    )

    url = service.create_photo_signed_url("abc123.jpg", expires_in=90)

    assert url == "https://personaldatabasen.blob.core.windows.net/images/abc123.jpg?sig=1"


def test_upload_photo_uses_azure() -> None:
    blob_client = FakeBlobClient(
        url="https://personaldatabasen.blob.core.windows.net/images/abc123.jpg"
    )
    container_client = FakeContainerClient(blob_client)
    blob_service_client = FakeBlobServiceClient(container_client)
    service = StorageService(
        Settings(
            azure_blob_connection_string="UseDevelopmentStorage=true",
            azure_blob_account_name="personaldatabasen",
            azure_blob_account_key="secret",
            azure_photo_container="images",
        ),
        blob_service_client=blob_service_client,
    )

    service.upload_photo("abc123.jpg", b"jpeg-bytes", "image/jpeg")

    assert blob_service_client.requested_containers == ["images"]
    assert container_client.requested_blob_names == ["abc123.jpg"]
    assert container_client.created is True
    assert blob_client.upload_calls == [
        {
            "content": b"jpeg-bytes",
            "overwrite": True,
            "content_type": "image/jpeg",
        }
    ]


def test_download_photo_uses_azure() -> None:
    blob_client = FakeBlobClient(
        url="https://personaldatabasen.blob.core.windows.net/images/abc123.jpg",
        download_content=b"jpeg-bytes",
    )
    service = StorageService(
        Settings(
            azure_blob_connection_string="UseDevelopmentStorage=true",
            azure_blob_account_name="personaldatabasen",
            azure_blob_account_key="secret",
            azure_photo_container="images",
        ),
        blob_service_client=FakeBlobServiceClient(FakeContainerClient(blob_client)),
    )

    content = service.download_photo("abc123.jpg")

    assert content == b"jpeg-bytes"


def test_remove_photo_uses_azure() -> None:
    blob_client = FakeBlobClient(
        url="https://personaldatabasen.blob.core.windows.net/images/abc123.jpg"
    )
    service = StorageService(
        Settings(
            azure_blob_connection_string="UseDevelopmentStorage=true",
            azure_blob_account_name="personaldatabasen",
            azure_blob_account_key="secret",
            azure_photo_container="images",
        ),
        blob_service_client=FakeBlobServiceClient(FakeContainerClient(blob_client)),
    )

    service.remove_photo("abc123.jpg")

    assert blob_client.deleted is True
