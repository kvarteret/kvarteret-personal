from datetime import UTC, date, datetime

import pytest

from app.services.people import PeopleService, PersonDetailShell


def _build_person_detail() -> PersonDetailShell:
    return PersonDetailShell(
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
    )


@pytest.mark.asyncio
async def test_person_detail_shell_uses_cache(monkeypatch):
    service = PeopleService(storage_service=object())  # type: ignore[arg-type]
    calls = 0

    async def fake_fetch(person_id: int):
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
            "arb_status": None,
            "sha1": None,
            "filetype": None,
        }

    monkeypatch.setattr(service.repository, "fetch_person_shell_row", fake_fetch)

    first = await service.get_person_detail_shell(1)
    second = await service.get_person_detail_shell(1)

    assert first is second
    assert first.full_name == "Test Person"
    assert calls == 1


@pytest.mark.asyncio
async def test_person_detail_shell_refetches_after_cache_expiry(monkeypatch):
    service = PeopleService(storage_service=object())  # type: ignore[arg-type]
    first_value = _build_person_detail()
    second_value = _build_person_detail()
    second_value.first_name = "Reloaded"  # type: ignore[misc]
    values = [first_value, second_value]

    async def fake_fetch_row(person_id: int):
        value = values.pop(0)
        return {
            "id": value.person_id,
            "fornavn": value.first_name,
            "etternavn": value.last_name,
            "epost": value.email,
            "telefon": value.phone,
            "fodselsdato": value.birth_date,
            "opprettet": value.created_at,
            "kjonn": value.gender,
            "gateadresse": value.address,
            "postnummerid": value.postal_code,
            "arb_status": value.employment_status,
            "sha1": None,
            "filetype": None,
        }

    monkeypatch.setattr(service.repository, "fetch_person_shell_row", fake_fetch_row)

    cached = await service.get_person_detail_shell(1)
    service._shell_cache.force_expire(1)
    reloaded = await service.get_person_detail_shell(1)

    assert cached.full_name == "Test Person"
    assert reloaded.full_name == "Reloaded Person"
