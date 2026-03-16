from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.dependencies import get_people_service
from app.main import create_app
from app.services.people import (
    CardItem,
    DocumentItem,
    MembershipItem,
    NextOfKinItem,
    PersonDetailShell,
    PersonListItem,
    PersonListPage,
    PersonRelations,
)
from tests.helpers import make_authenticated_user, override_authenticated_user


class FakePeopleService:
    async def list_people(self, query: str | None = None, limit: int = 50) -> list[PersonListItem]:
        return (await self.list_people_page(query=query, limit=limit, cursor=None)).items

    async def list_people_page(self, query: str | None = None, limit: int = 10, cursor: str | None = None) -> PersonListPage:
        return PersonListPage(
            items=[
                PersonListItem(
                    person_id=12,
                    first_name="Sample",
                    last_name="Person",
                    full_name="Sample Person",
                    email="person.one@example.test",
                    phone="00000000",
                    photo_url=None,
                )
            ],
            limit=limit,
            cursor=cursor,
            next_cursor="cursor-2" if cursor is None else None,
        )

    async def get_person_detail_shell(self, person_id: int) -> PersonDetailShell | None:
        if person_id != 12:
            return None
        return PersonDetailShell(
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
        )

    async def get_person_history(self, person_id: int, limit: int = 12) -> list[MembershipItem]:
        return [
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
        ]

    async def get_person_documents(self, person_id: int) -> list[DocumentItem]:
        return [
            DocumentItem(
                document_id=6,
                filename="certificate.pdf",
                filetype="pdf",
                group_id=7,
                created_at=datetime(2026, 3, 13, tzinfo=UTC),
                storage_path="12/certificate.pdf",
                download_url=None,
            )
        ]

    async def get_person_relations(self, person_id: int) -> PersonRelations:
        return PersonRelations(
            next_of_kin=[NextOfKinItem(next_of_kin_id=1, name="Contact Person", phone="00000001")],
            cards=[CardItem(card_id=3, card_number="CARD-42")],
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
    assert "Filtrer på navn" in list_response.text
    assert 'hx-trigger="keyup changed delay:80ms, search"' in list_response.text
    assert "Laster flere personer" in list_response.text
    assert detail_response.status_code == 200
    assert "Laster historikk" in detail_response.text
    assert "Laster filer" in detail_response.text
    assert "Laster kort og pårørende" in detail_response.text


def test_people_page_returns_partial_results_for_htmx() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_people_service] = lambda: FakePeopleService()
    client = TestClient(app)

    response = client.get("/people?q=sample", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "Sample Person" in response.text
    assert "<!DOCTYPE html>" not in response.text


def test_people_detail_partials_render_with_fake_service() -> None:
    app = create_app()
    override_authenticated_user(app, make_authenticated_user())
    app.dependency_overrides[get_people_service] = lambda: FakePeopleService()
    client = TestClient(app)

    history_response = client.get("/people/12/history")
    documents_response = client.get("/people/12/documents")
    relations_response = client.get("/people/12/relations")

    assert history_response.status_code == 200
    assert "Shift lead" in history_response.text
    assert documents_response.status_code == 200
    assert "certificate.pdf" in documents_response.text
    assert relations_response.status_code == 200
    assert "CARD-42" in relations_response.text
    assert "Contact Person" in relations_response.text
