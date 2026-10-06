"""Exercise aggregate output and access controls on migrated PostgreSQL."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.volunteers.queries import VolunteersQueries
from app.db.session import reset_request_session, set_request_session
from app.shared.semester import get_current_semester_code
from app.warehouse_counts import refresh_counts
from tests.e2e.conftest import requires_e2e_database

pytestmark = requires_e2e_database


async def personal_active_count(session):
    token = set_request_session(session)
    try:
        return await VolunteersQueries().count_volunteers(only_active=True)
    finally:
        reset_request_session(token)


async def test_active_count_matches_personal_with_trials_and_exclusions(
    e2e_engine, clean_database
):
    semester = get_current_semester_code()
    async with AsyncSession(e2e_engine) as session, session.begin():
        await session.execute(text("""
            INSERT INTO public.groups
                (id, slug, name, is_active, active_through_semester)
            VALUES (1, 'one', 'One', true, :semester)
        """), {"semester": semester})
        await session.execute(text("""
            INSERT INTO public.assignment_roles (id, name, group_id, penguin_points)
            VALUES (1, 'Member', 1, 0)
        """))
        await session.execute(text("""
            INSERT INTO public.volunteer_records (id, last_name, gender, created_at)
            SELECT id, 'Private name', 'U', now() FROM generate_series(1, 7) AS id
        """))
        # Signed member, unsigned member, active trial, excluded former member,
        # expired trial, historical-only member, and trial without assignment.
        await session.execute(text("""
            INSERT INTO public.role_assignments
                (id, volunteer_id, group_id, semester, contract_signed)
            VALUES (1, 1, 1, :semester, true), (2, 2, 1, :semester, false),
                   (3, 3, 1, :semester, false), (4, 4, 1, :semester, true),
                   (5, 5, 1, :semester, false), (6, 6, 1, :previous, true),
                   (7, 1, 1, :semester, true)
        """), {"semester": semester, "previous": semester - 10})
        await session.execute(text("""
            INSERT INTO public.volunteer_application_invites
                (id, token, email, source, status, promoted_volunteer_id, trial_ends_at)
            VALUES (1, 'one', 'one@example.invalid', 'test', 'trial', 3, now() + interval '1 day'),
                   (2, 'two', 'two@example.invalid', 'test', 'not_volunteer', 4, NULL),
                   (3, 'three', 'three@example.invalid', 'test', 'trial', 5, now() - interval '1 day'),
                   (4, 'four', 'four@example.invalid', 'test', 'trial', 7, now() + interval '1 day')
        """))
        await refresh_counts(session)
        active = await session.scalar(text("""
            SELECT volunteer_count FROM public.warehouse_volunteer_counts
            WHERE metric = 'active' AND semester = :semester
                AND scope_key = 'organisation'
        """), {"semester": semester})
        assert active == 3  # signed member plus the two active trials
        assert active == await personal_active_count(session)
        # Expiry is evaluated again on the next refresh, not frozen at creation.
        await session.execute(text("""
            UPDATE public.volunteer_application_invites
            SET trial_ends_at = now() - interval '1 day' WHERE status = 'trial'
        """))
        await refresh_counts(session)
        assert await session.scalar(text("""
            SELECT volunteer_count FROM public.warehouse_volunteer_counts
            WHERE metric = 'active'
        """)) == await personal_active_count(session) == 1


async def test_counts_deduplicate_suppress_and_remove_stale_rows(
    e2e_engine, clean_database
):
    async with AsyncSession(e2e_engine) as session, session.begin():
        await session.execute(text("""
            INSERT INTO public.groups
                (id, slug, name, is_active, active_through_semester)
            VALUES (1, 'one', 'One', true, 20262),
                   (2, 'two', 'Two', false, 20261)
        """))
        await session.execute(text("""
            INSERT INTO public.assignment_roles (id, name, group_id, penguin_points)
            VALUES (1, 'Member', 1, 0)
        """))
        await session.execute(text("""
            INSERT INTO public.volunteer_records (id, last_name, gender, created_at)
            SELECT id, 'Private name', 'U', now()
            FROM generate_series(1, 6) AS id
        """))
        await session.execute(text("""
            INSERT INTO public.role_assignments
                (id, volunteer_id, group_id, semester, contract_signed)
            VALUES (1, 1, 1, 20262, true), (2, 2, 1, 20262, true),
                   (3, 3, 1, 20262, true), (4, 4, 1, 20262, true),
                   (5, 5, 1, 20262, false), (6, 1, 1, 20262, true),
                   (7, 1, 2, 20262, true), (8, 6, 2, 20262, false),
                   (9, 1, 1, 20261, true)
        """))
        assert await refresh_counts(session) == 6
        rows = (await session.execute(text("""
            SELECT semester, scope_key, group_id, volunteer_count, is_suppressed
            FROM public.warehouse_volunteer_counts WHERE metric = 'assigned'
            ORDER BY semester, scope_key
        """))).tuples().all()
        assert rows == [
            (20261, "group:1", 1, None, True),
            (20261, "organisation", None, 1, False),
            (20262, "group:1", 1, 5, False),
            (20262, "group:2", 2, None, True),
            (20262, "organisation", None, 6, False),
        ]
        assert await session.scalar(text("""
            SELECT bool_and(refreshed_at = CURRENT_TIMESTAMP)
            FROM public.warehouse_volunteer_counts
        """))
        columns = (await session.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'warehouse_volunteer_counts'
        """))).scalars().all()
        assert set(columns) == {
            "metric", "semester", "scope_key", "group_id", "volunteer_count",
            "is_suppressed", "refreshed_at",
        }
        await session.execute(text("DELETE FROM public.role_assignments"))
        assert await refresh_counts(session) == 1
        assert await session.scalar(
            text("SELECT count(*) FROM public.warehouse_volunteer_counts WHERE metric = 'assigned'")
        ) == 0
        assert await session.scalar(text("""
            SELECT volunteer_count FROM public.warehouse_volunteer_counts
            WHERE metric = 'active'
        """)) == 0


async def test_export_is_not_public_and_failed_refresh_rolls_back(e2e_engine):
    async with AsyncSession(e2e_engine) as session, session.begin():
        await session.execute(text("DELETE FROM public.warehouse_volunteer_counts"))
        await session.execute(text("""
            INSERT INTO public.warehouse_volunteer_counts
            VALUES ('assigned', 20001, 'organisation', NULL, 42, false, now())
        """))
        with pytest.raises(RuntimeError, match="abort"):
            async with session.begin_nested():
                await refresh_counts(session)
                raise RuntimeError("abort")
        assert await session.scalar(text("""
            SELECT volunteer_count FROM public.warehouse_volunteer_counts
            WHERE semester = 20001 AND scope_key = 'organisation'
        """)) == 42
        assert await session.scalar(text("""
            SELECT relrowsecurity FROM pg_class
            WHERE oid = 'public.warehouse_volunteer_counts'::regclass
        """))
        for role in ("anon", "authenticated"):
            assert not await session.scalar(text("""
                SELECT has_table_privilege(:role,
                    'public.warehouse_volunteer_counts', 'SELECT')
            """), {"role": role})
        assert await session.scalar(text("""
            SELECT count(*) FROM pg_policies WHERE schemaname = 'public'
                AND tablename = 'warehouse_volunteer_counts'
        """)) == 0
