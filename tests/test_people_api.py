from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.cookies import sign_session_id
from app.auth.models import AuthenticatedUser, WebSession
from app.auth.roles import UserRole
from app.main import create_app
from app.services.people import (
    CardItem,
    DocumentItem,
    DocumentUploadResult,
    MembershipItem,
    NextOfKinItem,
    PersonDetail,
    PersonListItem,
    PhotoUploadResult,
)


class FakePeopleService:
    async def list_people(self, query: str | None = None, limit: int = 50) -> list[PersonListItem]:
        return [
            PersonListItem(
                person_id=12,
                first_name="Sample",
                last_name="Person",
                full_name="Sample Person",
                email="person.one@example.test",
                phone="00000000",
                birth_date=date(1815, 12, 10),
                created_at=datetime(2026, 3, 13, tzinfo=UTC),
                photo_url="https://example.test/person-one.jpg",
            )
        ]

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
            photo_url="https://example.test/person-one.jpg",
            documents=[
                DocumentItem(
                    document_id=6,
                    filename="certificate.pdf",
                    filetype="pdf",
                    group_id=7,
                    created_at=datetime(2026, 3, 13, tzinfo=UTC),
                    storage_path="12/certificate.pdf",
                    download_url="https://example.test/certificate.pdf",
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

    async def upload_photo(self, person_id: int, filename: str, content: bytes, content_type: str | None):
        return PhotoUploadResult(
            person_id=person_id,
            photo_url="/media/photos/person-one.jpg?token=test",
            storage_path="person-one.jpg",
        )

    async def delete_photo(self, person_id: int) -> None:
        return None

    async def upload_document(self, person_id: int, filename: str, content: bytes, content_type: str | None, group_id: int | None = None):
        return DocumentUploadResult(
            document_id=99,
            person_id=person_id,
            filename=filename,
            filetype="pdf",
            group_id=group_id,
            storage_path=f"{person_id}/{filename}",
            download_url=f"/media/documents/{person_id}/{filename}?token=test",
        )

    async def delete_document(self, document_id: int) -> None:
        return None


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


def _make_client() -> TestClient:
    app = create_app()
    app.state.people_service = FakePeopleService()
    app.state.session_store = FakeSessionStore()
    client = TestClient(app)
    client.cookies.set("kvarteret_session", sign_session_id("session-123"))
    return client


def test_people_api_returns_english_list_contract() -> None:
    client = _make_client()

    response = client.get("/api/v1/people?q=ada")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["person_id"] == 12
    assert payload[0]["first_name"] == "Sample"
    assert payload[0]["photo_url"] == "https://example.test/person-one.jpg"


def test_people_api_returns_detail_contract() -> None:
    client = _make_client()

    response = client.get("/api/v1/people/12")

    assert response.status_code == 200
    payload = response.json()
    assert payload["full_name"] == "Sample Person"
    assert payload["documents"][0]["storage_path"] == "12/certificate.pdf"
    assert payload["next_of_kin"][0]["name"] == "Contact Person"
    assert payload["recent_memberships"][0]["semester_label"] == "Fall 2026"


def test_people_api_returns_not_found_for_missing_person() -> None:
    client = _make_client()

    response = client.get("/api/v1/people/999")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "person_not_found"


def test_people_api_accepts_photo_and_document_uploads_for_admins() -> None:
    client = _make_client()

    photo_response = client.post(
        "/api/v1/people/12/photo",
        files={"file": ("person-one.jpg", b"jpg-bytes", "image/jpeg")},
    )
    document_response = client.post(
        "/api/v1/people/12/documents",
        data={"group_id": "7"},
        files={"file": ("certificate.pdf", b"pdf-bytes", "application/pdf")},
    )

    assert photo_response.status_code == 200
    assert photo_response.json()["photo_url"].startswith("/media/photos/")
    assert document_response.status_code == 200
    assert document_response.json()["storage_path"] == "12/certificate.pdf"
