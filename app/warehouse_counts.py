"""Rebuild aggregate counts before PostHog's full-refresh sync."""

from sqlalchemy import func, insert, literal, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.table_defs.warehouse import warehouse_volunteer_counts
from app.domain.volunteers.search_sql import current_active_volunteers_subquery
from app.domain.volunteers.tables import volunteer_records
from app.shared.semester import get_current_semester_code

REFRESH_SQL = """
INSERT INTO public.warehouse_volunteer_counts
    (metric, semester, scope_key, group_id, volunteer_count, is_suppressed, refreshed_at)
SELECT 'assigned', semester,
       CASE WHEN GROUPING(group_id) = 1 THEN 'organisation'
            ELSE 'group:' || group_id::text END,
       CASE WHEN GROUPING(group_id) = 1 THEN NULL ELSE group_id END,
       CASE WHEN GROUPING(group_id) = 0 AND COUNT(DISTINCT volunteer_id) < 5
            THEN NULL ELSE COUNT(DISTINCT volunteer_id) END,
       GROUPING(group_id) = 0 AND COUNT(DISTINCT volunteer_id) < 5,
       CURRENT_TIMESTAMP
FROM public.role_assignments
GROUP BY GROUPING SETS ((semester), (semester, group_id))
"""


async def refresh_counts(session: AsyncSession) -> int:
    # Serialize refreshers. DELETE + INSERT share the caller's transaction;
    # readers see the previous complete export until the replacement commits.
    await session.execute(
        text("LOCK TABLE public.warehouse_volunteer_counts IN EXCLUSIVE MODE")
    )
    await session.execute(text("DELETE FROM public.warehouse_volunteer_counts"))
    result = await session.execute(text(REFRESH_SQL))
    semester = get_current_semester_code()
    active = current_active_volunteers_subquery(semester_code=semester)
    # The same membership builder and volunteer-record join used by Personal's
    # current count. Aggregate in PostgreSQL; no identifiers leave the database.
    active_count = select(
        literal("active"), literal(semester), literal("organisation"),
        literal(None), func.count(), literal(False), func.current_timestamp(),
    ).select_from(
        volunteer_records.join(active, active.c.volunteer_id == volunteer_records.c.id)
    )
    await session.execute(insert(warehouse_volunteer_counts).from_select(
        ["metric", "semester", "scope_key", "group_id", "volunteer_count",
         "is_suppressed", "refreshed_at"],
        active_count,
    ))
    return result.rowcount + 1

