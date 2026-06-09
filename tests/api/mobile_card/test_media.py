from __future__ import annotations

from fastapi.testclient import TestClient
from PIL import Image

from app.auth.roles import UserRole
from app.dependencies import (
    get_current_user,
    get_mobile_card_service,
    get_volunteers_service,
)
from app.main import create_app
from app.media_tokens import (
    build_photo_media_url,
    sign_media_token,
)
from app.domain.mobile_card.service import MobileCardCurrentCardResult


def _build_jpeg_bytes() -> bytes:
    from io import BytesIO

    image = Image.new("RGB", (8, 8), (120, 80, 40))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    image.close()
    return buffer.getvalue()


JPEG_BYTES = _build_jpeg_bytes()


class FakeStorageService:
    def download_photo(self, path: str) -> bytes:
        if path != "abc123.jpg":
            raise FileNotFoundError(path)
        return JPEG_BYTES

class FakeVolunteersService:
    async def get_photo_storage_path(self, volunteer_id: int) -> str | None:
        if volunteer_id != 12:
            return None
        return "abc123.jpg"

    async def find_volunteer_id_by_email(self, email: str) -> int | None:
        if email == "volunteer@example.test":
            return 12
        return None


class FakeMobileCardService:
    async def get_current_card(self, session_token: str):
        if session_token != "token-123":
            from app.domain.mobile_card.service import MobileCardInvalidAccessCodeError

            raise MobileCardInvalidAccessCodeError("Unknown session token.")

        class Card:
            person_id = 12

        return MobileCardCurrentCardResult(card=Card())


def test_media_photo_route_returns_backend_bytes(monkeypatch) -> None:
    from app.media import router as media_module

    monkeypatch.setattr(
        media_module, "_get_storage_service", lambda request: FakeStorageService()
    )
    client = TestClient(create_app())

    response = client.get(build_photo_media_url("abc123.jpg"))

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert len(response.content) > 0
    assert response.headers["cache-control"] == "private, max-age=900"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["etag"] == '"photo-abc123-512"'


def test_media_route_rejects_invalid_token(monkeypatch) -> None:
    from app.media import router as media_module

    monkeypatch.setattr(
        media_module, "_get_storage_service", lambda request: FakeStorageService()
    )
    client = TestClient(create_app())
    token = sign_media_token(kind="photo", path="other.jpg")

    response = client.get(f"/media/photos/abc123.jpg?token={token}")

    assert response.status_code == 403


def test_media_document_route_is_removed() -> None:
    client = TestClient(create_app())
    token = sign_media_token(kind="document", path="12/certificate.pdf")

    response = client.get(f"/media/documents/12/certificate.pdf?token={token}")

    assert response.status_code == 404


def test_authenticated_image_route_allows_admin_session(monkeypatch) -> None:
    from app.media import router as media_module

    monkeypatch.setattr(
        media_module, "_get_storage_service", lambda request: FakeStorageService()
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: type(
        "User",
        (),
        {"email": "admin@example.test", "role": UserRole.ADMIN},
    )()
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_mobile_card_service] = lambda: FakeMobileCardService()
    client = TestClient(app)

    response = client.get("/images/12?size=128")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, max-age=3600"
    assert response.headers["vary"] == "Accept, Authorization, Cookie"
    assert response.headers["etag"] == '"photo-abc123-128"'


def test_authenticated_image_route_rejects_other_volunteer(monkeypatch) -> None:
    from app.media import router as media_module

    monkeypatch.setattr(
        media_module, "_get_storage_service", lambda request: FakeStorageService()
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: type(
        "User",
        (),
        {"email": "volunteer@example.test", "role": UserRole.VOLUNTEER},
    )()
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_mobile_card_service] = lambda: FakeMobileCardService()
    client = TestClient(app)

    response = client.get("/images/99")

    assert response.status_code == 403


def test_authenticated_image_route_allows_mobile_card_bearer(monkeypatch) -> None:
    from app.media import router as media_module

    monkeypatch.setattr(
        media_module, "_get_storage_service", lambda request: FakeStorageService()
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_mobile_card_service] = lambda: FakeMobileCardService()
    client = TestClient(app)

    response = client.get("/images/12", headers={"Authorization": "Bearer token-123"})

    assert response.status_code == 200


def test_authenticated_image_route_returns_304_when_etag_matches(monkeypatch) -> None:
    from app.media import router as media_module

    monkeypatch.setattr(
        media_module, "_get_storage_service", lambda request: FakeStorageService()
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: type(
        "User",
        (),
        {"email": "admin@example.test", "role": UserRole.ADMIN},
    )()
    app.dependency_overrides[get_volunteers_service] = lambda: FakeVolunteersService()
    app.dependency_overrides[get_mobile_card_service] = lambda: FakeMobileCardService()
    client = TestClient(app)

    response = client.get("/images/12", headers={"If-None-Match": '"photo-abc123-512"'})

    assert response.status_code == 304
    assert response.content == b""


def test_media_photo_route_falls_back_to_original_bytes_when_variant_rendering_fails(
    monkeypatch,
) -> None:
    from app.media import router as media_module

    media_module.PHOTO_VARIANT_CACHE.clear()
    monkeypatch.setattr(
        media_module, "_get_storage_service", lambda request: FakeStorageService()
    )
    monkeypatch.setattr(
        media_module,
        "render_photo_variant",
        lambda content, max_dimension: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    client = TestClient(create_app())

    response = client.get(build_photo_media_url("abc123.jpg"))

    assert response.status_code == 200
    assert response.content == JPEG_BYTES
    assert response.headers["content-type"] == "image/jpeg"
