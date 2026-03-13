from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.dependencies import get_people_service
from app.main import create_app
from app.services.people import CardItem, DocumentItem, MembershipItem, NextOfKinItem, PersonDetail, PersonListItem, PersonListPage
from tests.helpers import make_authenticated_user, override_authenticated_user


class FakePeopleService:
    async def list_people(self, query: str | None = None, limit: int = 50) -> list[PersonListItem]:
        return (await self.list_people_page(query=query, limit=limit, offset=0)).items

    async def list_people_page(self, query: str | None = None, limit: int = 10, offset: int = 0) -> PersonListPage:
        return PersonListPage(
            items=[
                PersonListItem(
                    person_id=12,
                    first_name="Sample",
                    last_name="Person",
                    full_name="Sample Person",
                    email="person.one@example.test",
                    phone="00000000",
                    birth_date=date(1815, 12, 10),
                    created_at=datetime(2026, 3, 13, tzinfo=UTC),
                    photo_url=None,
                )
            ],
            limit=limit,
            offset=offset,
            next_offset=10 if offset == 0 else None,
        )

    async def get_person_detail(self, person_id: int) -> PersonDetail | None:
        if person_id != 12:
            return None
        return PersonDetail(
            person_id=12,
            first_name="Sample",
            last_name="Person",
            full_name="Sample Person",
            email="person.one@example.test",
            phone="00000000",
            birth_date=date(1815, 12, 10),
            created_at=datetime(2026, 3, 13, tzinfo=UTC),
            gender="K",
            address="Example address",
            postal_code="0000",
            employment_status=1,
            photo_url=None,
            documents=[
                DocumentItem(
                    document_id=6,
                    filename="certificate.pdf",
                    filetype="pdf",
                    group_id=7,
                    created_at=datetime(2026, 3, 13, tzinfo=UTC),
                    storage_path="12/certificate.pdf",
                    download_url=None,
                )
            ],
            next_of_kin=[NextOfKinItem(next_of_kin_id=1, name="Contact Person", phone="00000001")],
            cards=[CardItem(card_id=3, card_number="CARD-42")],
            recent_memberships=[
                MembershipItem(
                    history_id=5,
                    group_id=9,
                    group_name="Bar",
                    role_id=2,
                    role_name="Shift lead",
                    semester_code=20262,
                    semester_label="Fall 2026",
                    contract_signed=True,
                )
            ],
        )


def test_people_pages_render_with_fake_service() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_people_service] = lambda: FakePeopleService()
    client = TestClient(app)

    list_response = client.get("/people")
    detail_response = client.get("/people/12")

    assert list_response.status_code == 200
    assert "Sample Person" in list_response.text
    assert "Search by name, email, or phone" in list_response.text
    assert 'hx-trigger="keyup changed delay:50ms, search"' in list_response.text
    assert "Loading more people" in list_response.text
    assert detail_response.status_code == 200
    assert "certificate.pdf" in detail_response.text
    assert "Next of kin" in detail_response.text
    assert "CARD-42" in detail_response.text


def test_people_page_returns_partial_results_for_htmx() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_people_service] = lambda: FakePeopleService()
    client = TestClient(app)

    response = client.get("/people?q=sample&offset=0", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "Sample Person" in response.text
    assert "<!DOCTYPE html>" not in response.text
