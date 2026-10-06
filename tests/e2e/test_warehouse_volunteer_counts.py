"""Exercise aggregate output and access controls on migrated PostgreSQL."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.refresh_warehouse_volunteer_counts import refresh_counts
from tests.e2e.conftest import requires_e2e_database

pytestmark = requires_e2e_database


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
        assert await refresh_counts(session) == 5
        rows = (await session.execute(text("""
            SELECT semester, scope_key, group_id, volunteer_count, is_suppressed
            FROM public.warehouse_volunteer_counts ORDER BY semester, scope_key
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
            "semester", "scope_key", "group_id", "volunteer_count",
            "is_suppressed", "refreshed_at",
        }
        await session.execute(text("DELETE FROM public.role_assignments"))
        assert await refresh_counts(session) == 0
        assert await session.scalar(
            text("SELECT count(*) FROM public.warehouse_volunteer_counts")
        ) == 0


async def test_export_is_not_public_and_failed_refresh_rolls_back(e2e_engine):
    async with AsyncSession(e2e_engine) as session, session.begin():
        await session.execute(text("DELETE FROM public.warehouse_volunteer_counts"))
        await session.execute(text("""
            INSERT INTO public.warehouse_volunteer_counts
            VALUES (20001, 'organisation', NULL, 42, false, now())
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
