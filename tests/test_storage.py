import httpx

from app.config import Settings
from app.services.storage import StorageService


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


def test_create_photo_signed_url_uses_photo_bucket() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"signedURL": "/object/sign/personnel-photos/abc123.jpg?token=1"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = StorageService(
        Settings(
            photo_bucket="personnel-photos",
            supabase_url="https://example.supabase.co",
            supabase_secret_key="key",
            azure_blob_connection_string=None,
            azure_blob_account_name=None,
            azure_blob_account_key=None,
        ),
        client=client,
    )

    url = service.create_photo_signed_url("abc123.jpg", expires_in=90)

    assert captured["method"] == "POST"
    assert captured["url"] == "https://example.supabase.co/storage/v1/object/sign/personnel-photos/abc123.jpg"
    assert "expiresIn" in str(captured["body"])
    assert url == "https://example.supabase.co/storage/v1/object/sign/personnel-photos/abc123.jpg?token=1"


def test_create_photo_signed_url_uses_azure_when_configured(monkeypatch) -> None:
    blob_client = FakeBlobClient(url="https://personaldatabasen.blob.core.windows.net/images/abc123.jpg")
    service = StorageService(
        Settings(
            azure_blob_connection_string="UseDevelopmentStorage=true",
            azure_blob_account_name="personaldatabasen",
            azure_blob_account_key="secret",
            azure_photo_container="images",
        ),
        blob_service_client=FakeBlobServiceClient(FakeContainerClient(blob_client)),
    )

    monkeypatch.setattr("app.services.storage.generate_blob_sas", lambda **kwargs: "sig=1")

    url = service.create_photo_signed_url("abc123.jpg", expires_in=90)

    assert url == "https://personaldatabasen.blob.core.windows.net/images/abc123.jpg?sig=1"


def test_upload_photo_uses_azure_when_configured() -> None:
    blob_client = FakeBlobClient(url="https://personaldatabasen.blob.core.windows.net/images/abc123.jpg")
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


def test_download_photo_uses_azure_when_configured() -> None:
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


def test_remove_photo_uses_azure_when_configured() -> None:
    blob_client = FakeBlobClient(url="https://personaldatabasen.blob.core.windows.net/images/abc123.jpg")
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


def test_create_document_signed_url_uses_document_bucket() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"data": {"signedUrl": "/object/sign/personnel-documents/12/certificate.pdf?token=2"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = StorageService(
        Settings(
            document_bucket="personnel-documents",
            supabase_url="https://example.supabase.co",
            supabase_secret_key="key",
            azure_blob_connection_string=None,
            azure_blob_account_name=None,
            azure_blob_account_key=None,
        ),
        client=client,
    )

    url = service.create_document_signed_url("12/certificate.pdf", expires_in=120)

    assert captured["url"] == "https://example.supabase.co/storage/v1/object/sign/personnel-documents/12/certificate.pdf"
    assert url == "https://example.supabase.co/storage/v1/object/sign/personnel-documents/12/certificate.pdf?token=2"


def test_upload_document_uses_document_bucket() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["content_type"] = request.headers["content-type"]
        captured["upsert"] = request.headers["x-upsert"]
        captured["body"] = request.content
        return httpx.Response(200, json={"Key": "12/certificate.pdf"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = StorageService(
        Settings(
            document_bucket="personnel-documents",
            supabase_url="https://example.supabase.co",
            supabase_secret_key="key",
            azure_blob_connection_string=None,
            azure_blob_account_name=None,
            azure_blob_account_key=None,
        ),
        client=client,
    )

    service.upload_document("12/certificate.pdf", b"pdf-bytes", "application/pdf")

    assert captured["method"] == "POST"
    assert captured["url"] == "https://example.supabase.co/storage/v1/object/personnel-documents/12/certificate.pdf"
    assert captured["upsert"] == "true"
    assert "multipart/form-data" in str(captured["content_type"])
    assert b"pdf-bytes" in captured["body"]


def test_remove_photo_uses_photo_bucket() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        return httpx.Response(200, json=[])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = StorageService(
        Settings(
            photo_bucket="personnel-photos",
            supabase_url="https://example.supabase.co",
            supabase_secret_key="key",
            azure_blob_connection_string=None,
            azure_blob_account_name=None,
            azure_blob_account_key=None,
        ),
        client=client,
    )

    service.remove_photo("abc123.jpg")

    assert captured["method"] == "DELETE"
    assert captured["url"] == "https://example.supabase.co/storage/v1/object/personnel-photos"
    assert "abc123.jpg" in str(captured["body"])
