from datetime import UTC, date, datetime

import pytest

from app.services.people import PeopleService, PersonDetail


def _build_person_detail() -> PersonDetail:
    return PersonDetail(
        person_id=1,
        first_name="Test",
        last_name="Person",
        full_name="Test Person",
        email="placeholder@example.test",
        phone=None,
        birth_date=date(2000, 1, 1),
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        gender="A",
        address=None,
        postal_code=None,
        employment_status=None,
        photo_url=None,
        documents=[],
        next_of_kin=[],
        cards=[],
        recent_memberships=[],
    )


@pytest.mark.asyncio
async def test_person_detail_uses_cache(monkeypatch):
    service = PeopleService(storage_service=object())  # type: ignore[arg-type]
    expected = _build_person_detail()
    calls = 0

    async def fake_fetch(person_id: int):
        nonlocal calls
        calls += 1
        return expected

    monkeypatch.setattr(service, "_fetch_person_detail", fake_fetch)

    first = await service.get_person_detail(1)
    second = await service.get_person_detail(1)

    assert first is expected
    assert second is expected
    assert calls == 1


@pytest.mark.asyncio
async def test_person_detail_refetches_after_cache_expiry(monkeypatch):
    service = PeopleService(storage_service=object())  # type: ignore[arg-type]
    first_value = _build_person_detail()
    second_value = _build_person_detail()
    second_value.full_name = "Reloaded Person"  # type: ignore[misc]
    values = [first_value, second_value]

    async def fake_fetch(person_id: int):
        return values.pop(0)

    monkeypatch.setattr(service, "_fetch_person_detail", fake_fetch)

    cached = await service.get_person_detail(1)
    service._detail_cache.force_expire(1)
    reloaded = await service.get_person_detail(1)

    assert cached is first_value
    assert reloaded is second_value
