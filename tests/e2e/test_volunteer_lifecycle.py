"""Volunteer application flows, end to end, on a real migrated Postgres.

The public prospect tests verify that every canonical group slug is
resolved through the real database and persisted as a group ID. The
full lifecycle tests then take two friends from public signup through
contact, trial, profile submission, independent promotion, and deletion.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re

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
        "SELECT first_choice_group_id, second_choice_group_id,"
        " first_choice_label, second_choice_label"
        " FROM public.volunteer_application_invites",
    )
    assert invites == [
        {
            "first_choice_group_id": expected_group_id,
            "second_choice_group_id": None,
            "first_choice_label": group_name,
            "second_choice_label": None,
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
        "SELECT first_choice_group_id, second_choice_group_id,"
        " first_choice_label, second_choice_label"
        " FROM public.volunteer_application_invites",
    )
    assert invites == [
        {
            "first_choice_group_id": first_group_id,
            "second_choice_group_id": second_group_id,
            "first_choice_label": "Debattkomiteen",
            "second_choice_label": "Festkomiteen",
        }
    ]


async def test_public_bar_choices_keep_distinct_metadata_and_route_primary_role(
    app,
    e2e_engine,
):
    group_id = await _seed_group(
        e2e_engine,
        slug="skjenke-gruppen",
        name="Skjenkegruppen",
    )
    async with e2e_engine.begin() as conn:
        role_id = (
            await conn.execute(
                text(
                    "INSERT INTO public.assignment_roles"
                    " (name, group_id, penguin_points, created_at)"
                    " VALUES ('Halvtimen-skjenker', :group_id, 0, :now)"
                    " RETURNING id"
                ),
                {"group_id": group_id, "now": datetime.now(timezone.utc)},
            )
        ).scalar_one()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://personal.e2e.test",
    ) as client:
        response = await client.post(
            "/api/v1/volunteer-prospects",
            json={
                "full_name": "Bar Choices",
                "email": "bar-choices@example.com",
                "phone": "+47 412 34 567",
                "study_institution": "UiB",
                "first_choice_group_slug": "halvtimen",
                "second_choice_group_slug": "grondahls",
            },
        )

    assert response.status_code == 201, response.text
    invites = await _fetch_all(
        e2e_engine,
        "SELECT initial_group_id, initial_role_id, first_choice_group_id,"
        " second_choice_group_id, first_choice_label, second_choice_label"
        " FROM public.volunteer_application_invites",
    )
    assert invites == [
        {
            "initial_group_id": group_id,
            "initial_role_id": role_id,
            "first_choice_group_id": group_id,
            "second_choice_group_id": group_id,
            "first_choice_label": "Halvtimen",
            "second_choice_label": "Grøndahls",
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
            (INVITER_EMAIL, "new", "public_signup"),
            (FRIEND_EMAIL, "new", "friend_invite"),
        ]
        inviter, friend = invites

        relationships = await _fetch_all(
            e2e_engine,
            "SELECT inviter_application_id, invitee_application_id,"
            " inviter_email_snapshot, invitee_email_snapshot"
            " FROM public.volunteer_application_friend_invitations ORDER BY id",
        )
        assert relationships == [
            {
                "inviter_application_id": inviter["id"],
                "invitee_application_id": friend["id"],
                "inviter_email_snapshot": INVITER_EMAIL,
                "invitee_email_snapshot": FRIEND_EMAIL,
            },
        ]

        # The applicant got a receipt, and the friend got an invitation with
        # their apply link.
        assert [e.recipient_email for e in email_outbox.sent] == [
            INVITER_EMAIL,
            FRIEND_EMAIL,
        ]
        assert email_outbox.sent[0].subject == "Den første døren er nå åpen"
        assert friend["token"] in email_outbox.sent[1].html_body

        # ── 2. Both must be contacted before starting trial ──────
        for invite in invites:
            response = await client.post(
                f"/volunteer-applications/{invite['id']}/contact",
                follow_redirects=False,
            )
            assert response.status_code == 303, response.text
            response = await client.post(
                f"/volunteer-applications/{invite['id']}/trial",
                follow_redirects=False,
            )
            assert response.status_code == 303, response.text

        statuses = await _fetch_all(
            e2e_engine,
            "SELECT status, trial_started_at, trial_ends_at "
            "FROM public.volunteer_application_invites ORDER BY id",
        )
        assert all(row["status"] == "trial" for row in statuses)
        assert all(row["trial_started_at"] is not None for row in statuses)
        assert all(row["trial_ends_at"] is not None for row in statuses)

        # Starting trial sends each applicant the profile-completion email.
        assert sorted(e.recipient_email for e in email_outbox.sent[2:]) == sorted(
            [FRIEND_EMAIL, INVITER_EMAIL]
        )

        # ── 3. Each application is independent ───────────────────
        # The inviter can be approved while the friend has not submitted.
        await _submit_profile(client, inviter["token"], first_name="Inga", last_name="Inviter")
        response = await client.post(
            f"/volunteer-applications/{inviter['id']}/approval",
            data={"accepted_group_id": str(group_id)},
        )
        assert response.status_code == 303, response.text

        statuses = await _fetch_all(
            e2e_engine,
            "SELECT email, status FROM public.volunteer_application_invites ORDER BY id",
        )
        assert [(row["email"], row["status"]) for row in statuses] == [
            (INVITER_EMAIL, "volunteer"),
            (FRIEND_EMAIL, "trial"),
        ]

        await _submit_profile(client, friend["token"], first_name="Frida", last_name="Friend")
        response = await client.post(
            f"/volunteer-applications/{friend['id']}/approval",
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

        # The removed group-level approval route is no longer part of the
        # application contract.
        response = await client.post(
            "/volunteer-applications/groups/1/approval",
            data={"accepted_group_id": str(group_id)},
        )
        assert response.status_code == 404

        promoted = await _fetch_all(
            e2e_engine,
            "SELECT status, promoted_volunteer_id FROM public.volunteer_application_invites ORDER BY id",
        )
        assert all(row["status"] == "volunteer" for row in promoted)
        assert all(row["promoted_volunteer_id"] is not None for row in promoted)

        # ── 4. The audit trail recorded every transition ──────────
        events = await _fetch_all(
            e2e_engine,
            "SELECT event_type, subject_id, actor_user_account_id FROM public.domain_events ORDER BY id",
        )
        event_types = [e["event_type"] for e in events]
        assert event_types == [
            "prospect_registered",
            "application_invited",
            "application_contacted",
            "trial_started",
            "application_contacted",
            "trial_started",
            "profile_completed",
            "application_approved",
            "profile_completed",
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
        assert all(row["status"] == "volunteer" for row in history)
        assert all(row["promoted_volunteer_id"] is None for row in history)
        # ...and they do not resurface as pending applications.
        pending = await _fetch_all(
            e2e_engine,
            "SELECT count(*) AS n FROM public.volunteer_application_invites i"
            " JOIN public.volunteer_application_submissions s"
            " ON s.invite_id = i.id WHERE i.status != 'volunteer'",
        )
        assert pending[0]["n"] == 0


async def test_deleting_unanswered_friend_keeps_relationship_snapshot(app, e2e_engine, email_outbox):
    await _seed_group(e2e_engine)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://personal.e2e.test") as client:
        await _signup_with_friend(client)
        invites = await _fetch_all(
            e2e_engine,
            "SELECT id, email FROM public.volunteer_application_invites ORDER BY id",
        )
        inviter, friend = invites

        response = await client.delete(
            f"/volunteer-applications/{friend['id']}",
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text

        remaining_invites = await _fetch_all(
            e2e_engine,
            "SELECT id, email FROM public.volunteer_application_invites ORDER BY id",
        )
        assert remaining_invites == [inviter]
        relationships = await _fetch_all(
            e2e_engine,
            "SELECT inviter_application_id, invitee_application_id,"
            " inviter_email_snapshot, invitee_email_snapshot"
            " FROM public.volunteer_application_friend_invitations",
        )
        assert relationships == [
            {
                "inviter_application_id": inviter["id"],
                "invitee_application_id": None,
                "inviter_email_snapshot": INVITER_EMAIL,
                "invitee_email_snapshot": FRIEND_EMAIL,
            },
        ]


async def test_active_trial_profile_gets_temporary_card_until_trial_expires(
    app,
    e2e_engine,
    email_outbox,
):
    await _seed_group(e2e_engine)
    email = "trial.card@example.com"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://personal.e2e.test",
    ) as client:
        response = await client.post(
            "/api/v1/volunteer-prospects",
            json={
                "full_name": "Trial Card",
                "email": email,
                "phone": "+47 412 34 567",
                "study_institution": "UiB",
                "first_choice_group_slug": GROUP_SLUG,
            },
        )
        assert response.status_code == 201, response.text
        application = (
            await _fetch_all(
                e2e_engine,
                "SELECT id, token FROM public.volunteer_application_invites",
            )
        )[0]

        for action in ("contact", "trial"):
            response = await client.post(
                f"/volunteer-applications/{application['id']}/{action}",
                follow_redirects=False,
            )
            assert response.status_code == 303, response.text
        await _submit_profile(
            client,
            application["token"],
            first_name="Trial",
            last_name="Card",
        )

        response = await client.post(
            "/api/v1/mobile-card/access-codes",
            json={"email": email},
        )
        assert response.status_code == 202, response.text
        code_match = re.search(
            r">\s*(\d{6})\s*<",
            email_outbox.sent[-1].html_body,
        )
        assert code_match is not None

        response = await client.post(
            "/api/v1/mobile-card/sessions",
            json={"email": email, "access_code": code_match.group(1)},
        )
        assert response.status_code == 200, response.text
        session = response.json()
        assert session["card"]["person_id"] == -application["id"]
        assert session["card"]["active_roles"][0]["signed_contract"] is False

        async with e2e_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE public.volunteer_application_invites "
                    "SET trial_ends_at = now() - interval '1 day' WHERE id = :id"
                ),
                {"id": application["id"]},
            )

        response = await client.get(
            "/api/v1/mobile-card/me",
            headers={"Authorization": f"Bearer {session['session_token']}"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Trial access has expired."
