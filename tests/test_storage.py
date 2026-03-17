import httpx

from app.config import Settings
from app.services.storage import StorageService


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
        ),
        client=client,
    )

    url = service.create_photo_signed_url("abc123.jpg", expires_in=90)

    assert captured["method"] == "POST"
    assert captured["url"] == "https://example.supabase.co/storage/v1/object/sign/personnel-photos/abc123.jpg"
    assert "expiresIn" in str(captured["body"])
    assert url == "https://example.supabase.co/storage/v1/object/sign/personnel-photos/abc123.jpg?token=1"


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
        ),
        client=client,
    )

    service.remove_photo("abc123.jpg")

    assert captured["method"] == "DELETE"
    assert captured["url"] == "https://example.supabase.co/storage/v1/object/personnel-photos"
    assert "abc123.jpg" in str(captured["body"])
