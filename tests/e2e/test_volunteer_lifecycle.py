"""Volunteer application flows, end to end, on a real migrated Postgres.

The public prospect tests verify that every canonical group slug is
resolved through the real database and persisted as a group ID. The
full lifecycle tests then take two friends from public signup through
profile submission, atomic approval, and deletion.

The failure-path test induces an error on the second member during
group approval and asserts the all-or-nothing property.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import text

from app.auth.roles import UserRole
from app.config import Settings
from app.dependencies import (
    get_current_user,
    require_authenticated_user,
    require_management_user,
)
from app.main import create_app
from app.runtime import build_application_container
from tests.support.helpers import make_authenticated_user

from tests.e2e.conftest import (
    E2E_DATABASE_URL,
    CapturingEmailSender,
    FakeStorageService,
    make_test_jpeg,
    requires_e2e_database,
)

pytestmark = requires_e2e_database

# Use example.com, not .test — Pydantic's EmailStr rejects the reserved
# .test TLD as a special-use name, which the public prospect API enforces.
INVITER_EMAIL = "inviter@example.com"
FRIEND_EMAIL = "friend@example.com"
GROUP_NAME = "Skjenkegruppen"
GROUP_SLUG = "skjenke-gruppen"
CANONICAL_GROUPS = [
    ("debatt", "Debattkomiteen"),
    ("fest", "Festkomiteen"),
    ("finans-departementet", "Finansdepartementet"),
    ("kommunikasjons-avdelingen", "Kommunikasjonsavdelingen"),
    ("skjenke-gruppen", GROUP_NAME),
    ("sosial-departementet", "Sosialdepartementet"),
]


@pytest.fixture
def email_outbox(monkeypatch) -> CapturingEmailSender:
    outbox = CapturingEmailSender()
    monkeypatch.setattr("app.runtime._build_email_sender", lambda settings: outbox)
    return outbox


@pytest.fixture
def storage(monkeypatch) -> FakeStorageService:
    fake = FakeStorageService()
    monkeypatch.setattr("app.runtime._build_storage_service", lambda settings: fake)
    return fake


@pytest.fixture
def app(clean_database, email_outbox, storage):
    settings = Settings(
        app_secret_key="e2e-secret",
        database_url=E2E_DATABASE_URL,
        app_public_base_url="https://personal.e2e.test",
    )
    container = build_application_container(settings)
    application = create_app(container)
    admin = make_authenticated_user(UserRole.ADMIN)
    application.dependency_overrides[get_current_user] = lambda: admin
    application.dependency_overrides[require_authenticated_user] = lambda: admin
    application.dependency_overrides[require_management_user] = lambda: admin
    return application


async def _seed_group(
    engine,
    *,
    slug: str = GROUP_SLUG,
    name: str = GROUP_NAME,
) -> int:
    async with engine.begin() as conn:
        row = await conn.execute(
            text(
                "INSERT INTO public.groups"
                " (slug, name, is_active, active_through_semester, created_at)"
                " VALUES (:slug, :name, true, 20991, :now) RETURNING id"
            ),
            {
                "slug": slug,
                "name": name,
                "now": datetime.now(timezone.utc),
            },
        )
        return row.scalar_one()


async def _fetch_all(engine, query: str, **params):
    async with engine.connect() as conn:
        result = await conn.execute(text(query), params)
        return result.mappings().all()


async def _signup_with_friend(client) -> None:
    response = await client.post(
        "/api/v1/volunteer-prospects",
        json={
            "full_name": "Inga Inviter",
            "email": INVITER_EMAIL,
            "phone": "+47 412 34 567",
            "study_institution": "UiB",
            "background_details": "Bartender",
            "first_choice_group_slug": GROUP_SLUG,
            "friend_emails": [FRIEND_EMAIL],
        },
    )
    assert response.status_code == 201, response.text


@pytest.mark.parametrize(("group_slug", "group_name"), CANONICAL_GROUPS)
async def test_public_prospect_accepts_every_canonical_group_slug(
    app,
    e2e_engine,
    group_slug,
    group_name,
):
    expected_group_id = await _seed_group(
        e2e_engine,
        slug=group_slug,
        name=group_name,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://personal.e2e.test",
    ) as client:
        response = await client.post(
            "/api/v1/volunteer-prospects",
            json={
                "full_name": "Canonical Applicant",
                "email": f"applicant-{group_slug}@example.com",
                "phone": "+47 412 34 567",
                "study_institution": "UiB",
                "first_choice_group_slug": group_slug,
            },
        )

    assert response.status_code == 201, response.text
    invites = await _fetch_all(
        e2e_engine,
        "SELECT first_choice_group_id, second_choice_group_id"
        " FROM public.volunteer_application_invites",
    )
    assert invites == [
        {
            "first_choice_group_id": expected_group_id,
            "second_choice_group_id": None,
        }
    ]


async def test_public_prospect_resolves_both_group_choices(app, e2e_engine):
    first_group_id = await _seed_group(
        e2e_engine,
        slug="debatt",
        name="Debattkomiteen",
    )
    second_group_id = await _seed_group(
        e2e_engine,
        slug="fest",
        name="Festkomiteen",
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://personal.e2e.test",
    ) as client:
        response = await client.post(
            "/api/v1/volunteer-prospects",
            json={
                "full_name": "Two Choices",
                "email": "two-choices@example.com",
                "phone": "+47 412 34 567",
                "study_institution": "UiB",
                "first_choice_group_slug": "debatt",
                "second_choice_group_slug": "fest",
            },
        )

    assert response.status_code == 201, response.text
    invites = await _fetch_all(
        e2e_engine,
        "SELECT first_choice_group_id, second_choice_group_id"
        " FROM public.volunteer_application_invites",
    )
    assert invites == [
        {
            "first_choice_group_id": first_group_id,
            "second_choice_group_id": second_group_id,
        }
    ]


async def test_public_prospect_rejects_unknown_group_without_persisting(
    app,
    e2e_engine,
):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://personal.e2e.test",
    ) as client:
        response = await client.post(
            "/api/v1/volunteer-prospects",
            json={
                "full_name": "Unknown Group",
                "email": "unknown-group@example.com",
                "phone": "+47 412 34 567",
                "study_institution": "UiB",
                "first_choice_group_slug": "does-not-exist",
            },
        )

    assert response.status_code == 400, response.text
    invites = await _fetch_all(
        e2e_engine,
        "SELECT id FROM public.volunteer_application_invites",
    )
    assert invites == []


async def _submit_profile(client, token: str, *, first_name: str, last_name: str):
    response = await client.post(
        f"/apply/{token}",
        data={
            "first_name": first_name,
            "last_name": last_name,
            "phone": "41234567",
            "birth_date": "2000-01-15",
            "gender": "A",
            "address": "Olav Kyrres gate 49",
            "postal_code": "5015",
        },
        files={"profile_photo": ("photo.jpg", make_test_jpeg(), "image/jpeg")},
    )
    assert response.status_code == 303, response.text


async def test_two_friend_lifecycle_until_deletion(app, e2e_engine, email_outbox):
    group_id = await _seed_group(e2e_engine)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://personal.e2e.test") as client:
        # ── 1. Public signup with a friend ────────────────────────
        await _signup_with_friend(client)

        invites = await _fetch_all(
            e2e_engine,
            "SELECT id, email, token, status, source FROM public.volunteer_application_invites ORDER BY id",
        )
        assert [(i["email"], i["status"], i["source"]) for i in invites] == [
            (INVITER_EMAIL, "prospect", "public_signup"),
            (FRIEND_EMAIL, "invited", "group_invite"),
        ]
        inviter, friend = invites

        members = await _fetch_all(
            e2e_engine,
            "SELECT applicant_email, role, status FROM public.volunteer_application_group_members ORDER BY id",
        )
        assert [(m["applicant_email"], m["role"], m["status"]) for m in members] == [
            (INVITER_EMAIL, "inviter", "active"),
            (FRIEND_EMAIL, "invitee", "active"),
        ]

        # The friend got an invitation email with their apply link.
        assert [e.recipient_email for e in email_outbox.sent] == [FRIEND_EMAIL]
        assert friend["token"] in email_outbox.sent[0].html_body

        # ── 2. Both submit their full profiles ────────────────────
        await _submit_profile(client, friend["token"], first_name="Frida", last_name="Friend")
        await _submit_profile(client, inviter["token"], first_name="Inga", last_name="Inviter")

        statuses = await _fetch_all(
            e2e_engine,
            "SELECT email, status FROM public.volunteer_application_invites ORDER BY id",
        )
        assert all(row["status"] == "submitted" for row in statuses)

        # Per-person approval of an active group member must be blocked.
        response = await client.post(
            f"/volunteer-applications/{inviter['id']}/approval",
            data={"accepted_group_id": str(group_id)},
        )
        assert response.status_code == 400
        assert "group approval" in response.text

        # ── 3. Atomic group approval into the committee ───────────
        group_row = await _fetch_all(e2e_engine, "SELECT id FROM public.volunteer_application_groups")
        application_group_id = group_row[0]["id"]
        response = await client.post(
            f"/volunteer-applications/groups/{application_group_id}/approval",
            data={"accepted_group_id": str(group_id)},
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text

        volunteers = await _fetch_all(
            e2e_engine,
            "SELECT id, first_name, last_name, email FROM public.volunteer_records ORDER BY id",
        )
        assert [(v["first_name"], v["email"]) for v in volunteers] == [
            ("Inga", INVITER_EMAIL),
            ("Frida", FRIEND_EMAIL),
        ]

        assignments = await _fetch_all(
            e2e_engine,
            "SELECT volunteer_id, group_id FROM public.role_assignments ORDER BY id",
        )
        assert [a["group_id"] for a in assignments] == [group_id, group_id]

        promoted = await _fetch_all(
            e2e_engine,
            "SELECT status, promoted_volunteer_id FROM public.volunteer_application_invites ORDER BY id",
        )
        assert all(row["status"] == "promoted" for row in promoted)
        assert all(row["promoted_volunteer_id"] is not None for row in promoted)

        # Both got profile-completion emails, after the commit.
        completion_recipients = sorted(e.recipient_email for e in email_outbox.sent[1:])
        assert completion_recipients == sorted([FRIEND_EMAIL, INVITER_EMAIL])

        # ── 4. The audit trail recorded every transition ──────────
        events = await _fetch_all(
            e2e_engine,
            "SELECT event_type, subject_id, actor_user_account_id FROM public.domain_events ORDER BY id",
        )
        event_types = [e["event_type"] for e in events]
        assert event_types == [
            "prospect_registered",
            "application_invited",
            "application_submitted",
            "application_submitted",
            "application_approved",
            "application_approved",
        ]
        approvals = [e for e in events if e["event_type"] == "application_approved"]
        assert all(e["actor_user_account_id"] == 5 for e in approvals)

        # ── 5. Offboarding: both volunteers are finally deleted ───
        for volunteer in volunteers:
            response = await client.delete(f"/volunteers/{volunteer['id']}", follow_redirects=False)
            assert response.status_code == 303, response.text

        remaining = await _fetch_all(e2e_engine, "SELECT id FROM public.volunteer_records")
        assert remaining == []
        # The application history rows survive as detached audit records.
        history = await _fetch_all(
            e2e_engine,
            "SELECT status, promoted_volunteer_id FROM public.volunteer_application_invites",
        )
        assert all(row["status"] == "promoted" for row in history)
        assert all(row["promoted_volunteer_id"] is None for row in history)
        # ...and they do not resurface as pending applications.
        pending = await _fetch_all(
            e2e_engine,
            "SELECT count(*) AS n FROM public.volunteer_application_invites i"
            " JOIN public.volunteer_application_submissions s"
            " ON s.invite_id = i.id WHERE i.status != 'promoted'",
        )
        assert pending[0]["n"] == 0


async def test_group_approval_is_atomic_when_second_member_fails(app, e2e_engine, email_outbox, monkeypatch):
    group_id = await _seed_group(e2e_engine)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://personal.e2e.test") as client:
        await _signup_with_friend(client)
        invites = await _fetch_all(
            e2e_engine,
            "SELECT id, token FROM public.volunteer_application_invites ORDER BY id",
        )
        for index, invite in enumerate(invites):
            await _submit_profile(
                client,
                invite["token"],
                first_name=f"Member{index}",
                last_name="Test",
            )
        emails_before = len(email_outbox.sent)

        # Approval now creates volunteers through the volunteers module's
        # onboarding port; fail there on the second member.
        volunteers = app.state.container.volunteers_service
        real_create = volunteers.create_from_application
        calls = {"n": 0}

        async def flaky_create(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("induced failure on second member")
            return await real_create(**kwargs)

        monkeypatch.setattr(volunteers, "create_from_application", flaky_create)

        group_row = await _fetch_all(e2e_engine, "SELECT id FROM public.volunteer_application_groups")
        with pytest.raises(RuntimeError, match="induced failure"):
            await client.post(
                f"/volunteer-applications/groups/{group_row[0]['id']}/approval",
                data={"accepted_group_id": str(group_id)},
            )

        # All or nothing: the first member's promotion rolled back too.
        volunteers = await _fetch_all(e2e_engine, "SELECT id FROM public.volunteer_records")
        assert volunteers == []
        statuses = await _fetch_all(
            e2e_engine,
            "SELECT status FROM public.volunteer_application_invites",
        )
        assert all(row["status"] == "submitted" for row in statuses)
        approval_events = await _fetch_all(
            e2e_engine,
            "SELECT id FROM public.domain_events WHERE event_type = 'application_approved'",
        )
        assert approval_events == []
        # No promotion emails were sent for the failed attempt.
        assert len(email_outbox.sent) == emails_before
