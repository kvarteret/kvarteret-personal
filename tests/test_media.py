from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.media_tokens import build_document_media_url, build_photo_media_url, sign_media_token


class FakeStorageService:
    def download_photo(self, path: str) -> bytes:
        if path != "abc123.jpg":
            raise FileNotFoundError(path)
        return b"fake-jpeg"

    def download_document(self, path: str) -> bytes:
        if path != "12/certificate.pdf":
            raise FileNotFoundError(path)
        return b"%PDF-1.7 fake"


def test_media_photo_route_returns_backend_bytes(monkeypatch) -> None:
    from app.api import media as media_module

    monkeypatch.setattr(media_module, "get_storage_service", lambda: FakeStorageService())
    client = TestClient(create_app())

    response = client.get(build_photo_media_url("abc123.jpg"))

    assert response.status_code == 200
    assert response.content == b"fake-jpeg"
    assert response.headers["content-type"] == "image/jpeg"


def test_media_document_route_returns_backend_bytes(monkeypatch) -> None:
    from app.api import media as media_module

    monkeypatch.setattr(media_module, "get_storage_service", lambda: FakeStorageService())
    client = TestClient(create_app())

    response = client.get(build_document_media_url("12/certificate.pdf"))

    assert response.status_code == 200
    assert response.content == b"%PDF-1.7 fake"
    assert response.headers["content-type"] == "application/pdf"


def test_media_route_rejects_invalid_token(monkeypatch) -> None:
    from app.api import media as media_module

    monkeypatch.setattr(media_module, "get_storage_service", lambda: FakeStorageService())
    client = TestClient(create_app())
    token = sign_media_token(kind="photo", path="other.jpg")

    response = client.get(f"/media/photos/abc123.jpg?token={token}")

    assert response.status_code == 403
