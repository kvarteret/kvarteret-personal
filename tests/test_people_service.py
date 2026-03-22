from datetime import UTC, date, datetime
from io import BytesIO

import pytest
from PIL import Image

from app.services.volunteers import VolunteersService, VolunteerDetail


def _build_png_bytes() -> bytes:
    image = Image.new("RGBA", (8, 8), (12, 34, 56, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    image.close()
    return buffer.getvalue()


PNG_BYTES = _build_png_bytes()


def _build_person_detail() -> VolunteerDetail:
    return VolunteerDetail(
        volunteer_id=1,
        first_name="Test",
        last_name="Person",
        full_name="Test Person",
        email="placeholder@example.test",
        phone=None,
        birth_date=date(2000, 1, 1),
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        gender_code="A",
        gender_label="Annet",
        address=None,
        postal_code=None,
        pingvin_points=0,
        photo_url=None,
    )


@pytest.mark.asyncio
async def test_person_detail_shell_uses_cache(monkeypatch):
    service = VolunteersService(storage_service=object())  # type: ignore[arg-type]
    calls = 0

    async def fake_fetch(volunteer_id: int):
        nonlocal calls
        calls += 1
        return {
            "id": 1,
            "fornavn": "Test",
            "etternavn": "Person",
            "epost": "placeholder@example.test",
            "telefon": None,
            "fodselsdato": date(2000, 1, 1),
            "opprettet": datetime(2024, 1, 1, tzinfo=UTC),
            "kjonn": "A",
            "gateadresse": None,
            "postnummerid": None,
            "pingvin_points": 0,
            "sha1": None,
            "filetype": None,
        }

    monkeypatch.setattr(service.repository, "fetch_volunteer_shell_row", fake_fetch)

    first = await service.get_volunteer_detail(1)
    second = await service.get_volunteer_detail(1)

    assert first is second
    assert first is not None
    assert first.full_name == "Test Person"
    assert calls == 1


@pytest.mark.asyncio
async def test_person_detail_shell_refetches_after_cache_expiry(monkeypatch):
    service = VolunteersService(storage_service=object())  # type: ignore[arg-type]
    first_value = _build_person_detail()
    second_value = _build_person_detail()
    second_value.first_name = "Reloaded"
    values = [first_value, second_value]

    async def fake_fetch_row(volunteer_id: int):
        value = values.pop(0)
        return {
            "id": value.volunteer_id,
            "fornavn": value.first_name,
            "etternavn": value.last_name,
            "epost": value.email,
            "telefon": value.phone,
            "fodselsdato": value.birth_date,
            "opprettet": value.created_at,
            "kjonn": value.gender_code,
            "gateadresse": value.address,
            "postnummerid": value.postal_code,
            "pingvin_points": value.pingvin_points,
            "sha1": None,
            "filetype": None,
        }

    monkeypatch.setattr(service.repository, "fetch_volunteer_shell_row", fake_fetch_row)

    cached = await service.get_volunteer_detail(1)
    service._shell_cache.force_expire(1)
    reloaded = await service.get_volunteer_detail(1)

    assert cached is not None
    assert reloaded is not None
    assert cached.full_name == "Test Person"
    assert reloaded.full_name == "Reloaded Person"


@pytest.mark.asyncio
async def test_search_cursor_offset_is_clamped(monkeypatch):
    service = VolunteersService(storage_service=object())  # type: ignore[arg-type]
    seen: dict[str, int] = {}

    async def fake_search(*, normalized_query: str, limit: int, offset: int):
        seen["offset"] = offset
        return []

    monkeypatch.setattr(service.repository, "search_volunteers_page", fake_search)

    cursor = "eyJtb2RlIjoic2VhcmNoIiwib2Zmc2V0Ijo5OTk5OTl9"
    page = await service.list_volunteers_page(query="person", limit=10, cursor=cursor)

    assert seen["offset"] == 10_000
    assert page.items == []


@pytest.mark.asyncio
async def test_upload_photo_normalizes_to_jpeg_before_storage() -> None:
    uploaded: dict[str, object] = {}
    saved_record: dict[str, object] = {}

    class FakeRepository:
        async def volunteer_exists(self, volunteer_id: int) -> bool:
            return volunteer_id == 1

        async def fetch_photo_record(self, volunteer_id: int):
            return None

        async def save_photo_record(self, *, volunteer_id: int, filename_hash: str, extension: str, existing: bool) -> None:
            saved_record.update(
                {
                    "volunteer_id": volunteer_id,
                    "filename_hash": filename_hash,
                    "extension": extension,
                    "existing": existing,
                }
            )

    class FakeStorage:
        def upload_photo(self, path: str, content: bytes, content_type: str | None = None) -> None:
            uploaded.update(
                {
                    "path": path,
                    "content": content,
                    "content_type": content_type,
                }
            )

        def remove_photo(self, path: str) -> None:
            raise AssertionError("remove_photo should not be called")

    class FakeMediaTokenService:
        def build_photo_media_url(self, path: str) -> str:
            return f"/media/photos/{path}?token=test"

    service = VolunteersService(
        repository=FakeRepository(),  # type: ignore[arg-type]
        storage_service=FakeStorage(),  # type: ignore[arg-type]
        media_token_service=FakeMediaTokenService(),  # type: ignore[arg-type]
    )

    result = await service.upload_photo(
        volunteer_id=1,
        filename="avatar.png",
        content=PNG_BYTES,
        content_type="image/png",
    )

    assert uploaded["path"].endswith(".jpg")
    assert uploaded["content_type"] == "image/jpeg"
    assert isinstance(uploaded["content"], bytes)
    assert len(uploaded["content"]) > 0
    assert saved_record["extension"] == "jpg"
    assert result.storage_path.endswith(".jpg")
    assert result.photo_url.endswith(".jpg?token=test")
