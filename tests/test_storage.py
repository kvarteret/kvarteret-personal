from app.config import Settings
from app.services.storage import StorageService


class FakeBucket:
    def __init__(self) -> None:
        self.last_path: str | None = None
        self.last_expires_in: int | None = None
        self.last_upload_path: str | None = None
        self.last_upload_content: bytes | None = None
        self.last_upload_options: dict | None = None
        self.last_removed_paths: list[str] | None = None

    def create_signed_url(self, path: str, expires_in: int) -> dict:
        self.last_path = path
        self.last_expires_in = expires_in
        return {"data": {"signedUrl": f"https://example.test/{path}?exp={expires_in}"}}

    def upload(self, path: str, file: bytes, file_options: dict | None = None) -> dict:
        self.last_upload_path = path
        self.last_upload_content = file
        self.last_upload_options = file_options
        return {"path": path}

    def remove(self, paths: list[str]) -> list[str]:
        self.last_removed_paths = paths
        return paths


class FakeStorage:
    def __init__(self, bucket: FakeBucket) -> None:
        self.bucket = bucket
        self.bucket_name: str | None = None

    def from_(self, bucket_name: str) -> FakeBucket:
        self.bucket_name = bucket_name
        return self.bucket


class FakeClient:
    def __init__(self, bucket: FakeBucket) -> None:
        self.storage = FakeStorage(bucket)


def test_create_photo_signed_url_uses_photo_bucket() -> None:
    bucket = FakeBucket()
    client = FakeClient(bucket)
    service = StorageService(
        Settings(
            photo_bucket="personnel-photos",
            supabase_url="https://example.supabase.co",
            supabase_secret_key="key",
        ),
        client=client,
    )

    url = service.create_photo_signed_url("abc123.jpg", expires_in=90)

    assert client.storage.bucket_name == "personnel-photos"
    assert bucket.last_path == "abc123.jpg"
    assert bucket.last_expires_in == 90
    assert url == "https://example.test/abc123.jpg?exp=90"


def test_create_document_signed_url_uses_document_bucket() -> None:
    bucket = FakeBucket()
    client = FakeClient(bucket)
    service = StorageService(
        Settings(
            document_bucket="personnel-documents",
            supabase_url="https://example.supabase.co",
            supabase_secret_key="key",
        ),
        client=client,
    )

    url = service.create_document_signed_url("12/certificate.pdf", expires_in=120)

    assert client.storage.bucket_name == "personnel-documents"
    assert bucket.last_path == "12/certificate.pdf"
    assert bucket.last_expires_in == 120
    assert url == "https://example.test/12/certificate.pdf?exp=120"


def test_upload_document_uses_document_bucket() -> None:
    bucket = FakeBucket()
    client = FakeClient(bucket)
    service = StorageService(
        Settings(
            document_bucket="personnel-documents",
            supabase_url="https://example.supabase.co",
            supabase_secret_key="key",
        ),
        client=client,
    )

    service.upload_document("12/certificate.pdf", b"pdf-bytes", "application/pdf")

    assert client.storage.bucket_name == "personnel-documents"
    assert bucket.last_upload_path == "12/certificate.pdf"
    assert bucket.last_upload_content == b"pdf-bytes"
    assert bucket.last_upload_options == {"upsert": "true", "content-type": "application/pdf"}


def test_remove_photo_uses_photo_bucket() -> None:
    bucket = FakeBucket()
    client = FakeClient(bucket)
    service = StorageService(
        Settings(
            photo_bucket="personnel-photos",
            supabase_url="https://example.supabase.co",
            supabase_secret_key="key",
        ),
        client=client,
    )

    service.remove_photo("abc123.jpg")

    assert client.storage.bucket_name == "personnel-photos"
    assert bucket.last_removed_paths == ["abc123.jpg"]
