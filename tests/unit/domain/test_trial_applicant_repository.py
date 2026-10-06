from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.metadata import public_metadata
from app.db.session import reset_request_session, set_request_session
from app.domain.mobile_card.repository import MobileCardRepository
from app.domain.groups.tables import groups
from app.domain.role_assignments.tables import assignment_roles
from app.domain.volunteer_applications.models import VolunteerApplicationSubmissionInput
from app.domain.volunteer_applications.repository import VolunteerApplicationsRepository
from app.domain.volunteer_applications.tables import (
    volunteer_application_invites,
    volunteer_application_submissions,
)
from app.domain.volunteers.tables import volunteer_photos, volunteer_records


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        execution_options={"schema_translate_map": {"public": None}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda conn: public_metadata.create_all(
                conn,
                tables=[
                    groups,
                    assignment_roles,
                    volunteer_records,
                    volunteer_photos,
                    volunteer_application_invites,
                    volunteer_application_submissions,
                ],
            )
        )
    async with async_sessionmaker(engine)() as session:
        token = set_request_session(session)
        try:
            now = datetime.now(UTC)
            await session.execute(
                insert(groups).values(
                    id=1,
                    slug="bar",
                    name="Bar",
                    discount_tier=2,
                    is_active=True,
                    active_through_semester=20992,
                )
            )
            await session.execute(
                insert(volunteer_records).values(
                    id=12,
                    email="ada@example.com",
                    first_name="Ada",
                    last_name="Updated",
                    gender="A",
                    created_at=now,
                )
            )
            await session.execute(
                insert(volunteer_application_invites).values(
                    id=7,
                    token="trial-token",
                    email="ada@example.com",
                    source="public",
                    status="trial",
                    trial_shift_attended=False,
                    created_at=now,
                    trial_ends_at=now + timedelta(days=30),
                    promoted_volunteer_id=12,
                    owns_volunteer_profile=True,
                    first_choice_group_id=1,
                )
            )
            yield session
        finally:
            reset_request_session(token)
    await engine.dispose()


async def test_incomplete_linked_profile_can_get_trial_card(session):
    repository = VolunteerApplicationsRepository()
    snapshot = await repository.find_active_trial_applicant_by_email("ada@example.com")
    assert snapshot is not None
    assert snapshot.volunteer_id == 12
    assert snapshot.last_name == "Updated"
    assert snapshot.photo_path is None
    assert snapshot.discount_level == 2
    assert await repository.get_active_trial_applicant(7) == snapshot


async def test_trial_card_uses_linked_profile_instead_of_stale_submission(session):
    await session.execute(
        insert(volunteer_application_submissions).values(
            id=1,
            invite_id=7,
            created_at=datetime.now(UTC),
            first_name="Old",
            last_name="Old",
            email="ada@example.com",
            gender="A",
            photo_sha1="old",
            photo_filetype="jpg",
        )
    )
    await session.execute(
        insert(volunteer_photos).values(volunteer_id=12, sha1="new", filetype="png")
    )
    snapshot = await VolunteerApplicationsRepository().get_active_trial_applicant(7)
    assert snapshot.first_name == "Ada"
    assert snapshot.photo_path == "new.png"


@pytest.mark.parametrize(
    "status,days",
    [("trial", -1), ("not_volunteer", 30), ("contacted", 30), ("volunteer", 30)],
)
async def test_only_unexpired_trials_get_trial_cards(session, status, days):
    await session.execute(
        update(volunteer_application_invites).values(
            status=status,
            trial_ends_at=datetime.now(UTC) + timedelta(days=days),
        )
    )
    assert await VolunteerApplicationsRepository().get_active_trial_applicant(7) is None


async def test_profile_submission_during_trial_updates_both_records(session):
    await session.execute(
        insert(volunteer_application_submissions).values(
            id=1,
            invite_id=7,
            created_at=datetime.now(UTC),
            first_name="Old",
            last_name="Old",
            email="ada@example.com",
            gender="A",
            studiested="UiB",
            bakgrunn="Experience",
        )
    )
    submission = VolunteerApplicationSubmissionInput(
        first_name="Ada",
        last_name="Complete",
        gender="A",
        birth_date=date(2000, 1, 1),
        address="Street 1",
        postal_code="5000",
        phone="+4741234567",
    )
    await VolunteerApplicationsRepository().save_submission(
        registration_id=7,
        email="ada@example.com",
        submission=submission,
        photo_sha1="new",
        photo_filetype="jpg",
    )
    stored = (
        (await session.execute(select(volunteer_application_submissions)))
        .mappings()
        .one()
    )
    volunteer = (await session.execute(select(volunteer_records))).mappings().one()
    assert stored["last_name"] == volunteer["last_name"] == "Complete"
    assert stored["street_address"] == volunteer["street_address"] == "Street 1"
    assert stored["photo_sha1"] == "new"
    assert stored["studiested"] == "UiB"
    assert stored["bakgrunn"] == "Experience"
    assert (
        await session.scalar(
            select(volunteer_application_invites.c.full_profile_submitted_at)
        )
    ) is not None


@pytest.mark.parametrize(
    "status", ["new", "contacted", "trial", "not_volunteer", "volunteer"]
)
async def test_linked_applicants_get_ordinary_login_only_after_approval(
    session, status
):
    await session.execute(update(volunteer_application_invites).values(status=status))
    volunteers = await MobileCardRepository().find_volunteers_by_email(
        "ada@example.com"
    )
    assert bool(volunteers) is (status == "volunteer")


async def test_trial_card_can_use_legacy_submission_birth_date(session):
    await session.execute(
        insert(volunteer_application_submissions).values(
            id=1,
            invite_id=7,
            created_at=datetime.now(UTC),
            first_name="Old",
            last_name="Old",
            email="ada@example.com",
            gender="A",
            birth_date=datetime(2000, 1, 1, tzinfo=UTC),
        )
    )
    snapshot = await VolunteerApplicationsRepository().get_active_trial_applicant(7)
    assert snapshot.birth_date == date(2000, 1, 1)


@pytest.mark.parametrize(
    "status,approved",
    [
        ("trial", False),
        ("not_volunteer", True),
        ("contacted", True),
        ("volunteer", False),
        ("volunteer", True),
    ],
)
async def test_session_handoff_requires_actual_approval_of_same_application(
    session, status, approved
):
    await session.execute(
        update(volunteer_application_invites).values(
            status=status,
            promoted_at=datetime.now(UTC) if approved else None,
        )
    )
    repository = VolunteerApplicationsRepository()
    assert await repository.get_approved_volunteer_id(7) == (
        12 if status == "volunteer" and approved else None
    )
    assert await repository.get_approved_volunteer_id(999) is None
