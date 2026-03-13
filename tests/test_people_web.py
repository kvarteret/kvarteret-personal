from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.cookies import sign_session_id
from app.auth.models import AuthenticatedUser, WebSession
from app.auth.roles import UserRole
from app.main import create_app
from app.services.people import CardItem, DocumentItem, MembershipItem, NextOfKinItem, PersonDetail, PersonListItem, PersonListPage


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


class FakeSessionStore:
    async def load_authenticated_user(self, session_id: str):
        return (
            WebSession(
                session_id=session_id,
                auth_user_id=uuid4(),
                user_account_id=5,
                expires_at=datetime.now(UTC) + timedelta(hours=12),
            ),
            AuthenticatedUser(
                auth_user_id=uuid4(),
                user_account_id=5,
                username="admin",
                email="admin.user@example.test",
                display_name="System User",
                role=UserRole.ADMIN,
            ),
        )

    async def delete_session(self, session_id: str) -> None:
        return None


def test_people_pages_render_with_fake_service() -> None:
    app = create_app()
    app.state.people_service = FakePeopleService()
    app.state.session_store = FakeSessionStore()
    client = TestClient(app)
    client.cookies.set("kvarteret_session", sign_session_id("session-123"))

    list_response = client.get("/people")
    detail_response = client.get("/people/12")

    assert list_response.status_code == 200
    assert "Sample Person" in list_response.text
    assert "Search by name, email, or phone" in list_response.text
    assert 'hx-trigger="keyup changed delay:50ms, search"' in list_response.text
    assert 'Loading more people' in list_response.text
    assert detail_response.status_code == 200
    assert "certificate.pdf" in detail_response.text
    assert "Next of kin" in detail_response.text
    assert "CARD-42" in detail_response.text


def test_people_page_returns_partial_results_for_htmx() -> None:
    app = create_app()
    app.state.people_service = FakePeopleService()
    app.state.session_store = FakeSessionStore()
    client = TestClient(app)
    client.cookies.set("kvarteret_session", sign_session_id("session-123"))

    response = client.get("/people?q=sample&offset=0", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "Sample Person" in response.text
    assert "<!DOCTYPE html>" not in response.text
