from __future__ import annotations

from datetime import date

from sqlalchemy import and_, exists, func, not_, or_, select

from app.db.repository import SqlAlchemyRepository
from app.db.tables import historie, historie_kurs, personal, verv
from app.shared.coercion import coerce_date
from app.shared.text import build_full_name
from app.domain.search.models import SearchFilterList, SearchQuery, SearchResultItem
from app.infrastructure.formatting.semester import format_semester_code


class VolunteerSearchRepository(SqlAlchemyRepository):
    async def search_volunteers(self, query: SearchQuery) -> list[SearchResultItem]:
        points = _pingvin_points_subquery()
        last_semesters = _last_semester_subquery()
        stmt = (
            select(
                personal.c.id,
                personal.c.fornavn,
                personal.c.etternavn,
                personal.c.fodselsdato,
                personal.c.telefon,
                personal.c.epost,
                func.coalesce(points.c.pingvin_points, 0).label("pingvin_points"),
                last_semesters.c.last_semester,
            )
            .select_from(
                personal.outerjoin(points, points.c.id_personal == personal.c.id).outerjoin(
                    last_semesters, last_semesters.c.id_personal == personal.c.id
                )
            )
            .where(*_build_filters(query, points))
            .order_by(personal.c.id.desc())
            .limit(500)
        )
        rows = await self.fetch_all_mappings(stmt)
        return [
            SearchResultItem(
                volunteer_id=row["id"],
                first_name=row.get("fornavn"),
                last_name=row["etternavn"],
                full_name=build_full_name(row.get("fornavn"), row["etternavn"]),
                pingvin_points=int(row.get("pingvin_points") or 0),
                last_semester_code=row.get("last_semester"),
                last_semester_label=format_semester_code(row.get("last_semester")),
                birth_date=coerce_date(row.get("fodselsdato")),
                phone=row.get("telefon"),
                email=row.get("epost"),
            )
            for row in rows
        ]


def _build_filters(query: SearchQuery, points) -> list:
    filters = []
    if query.birth_date_after is not None:
        filters.append(personal.c.fodselsdato >= query.birth_date_after)
    if query.birth_date_before is not None:
        filters.append(personal.c.fodselsdato <= query.birth_date_before)

    if query.pingvin_points_above is not None:
        filters.append(func.coalesce(points.c.pingvin_points, 0) > query.pingvin_points_above)
    if query.pingvin_points_below is not None:
        filters.append(func.coalesce(points.c.pingvin_points, 0) < query.pingvin_points_below)

    filters.extend(
        [
            _active_signed_contract_filter(query.has_active_signed_contract),
            _membership_filter(query.include_groups, semester_code=None, include_mode=True),
            _membership_filter(query.include_current_groups, semester_code=_get_current_semester_code(), include_mode=True),
            _membership_filter(query.exclude_groups, semester_code=None, include_mode=False),
            _membership_filter(
                query.exclude_current_groups,
                semester_code=_get_current_semester_code(),
                include_mode=False,
            ),
            _course_filter(query.include_courses, include_mode=True),
            _course_filter(query.exclude_courses, include_mode=False),
        ]
    )
    return [filter_clause for filter_clause in filters if filter_clause is not None]


def _active_signed_contract_filter(enabled: bool):
    if not enabled:
        return None

    return exists(
        select(1)
        .select_from(historie)
        .where(historie.c.id_personal == personal.c.id)
        .where(historie.c.semester == _get_current_semester_code())
        .where(historie.c.signert_kontrakt.is_(True))
    )


def _membership_filter(
    filter_list: SearchFilterList | None,
    *,
    semester_code: int | None,
    include_mode: bool,
):
    return _related_filter(
        filter_list,
        include_mode=include_mode,
        build_exists=lambda filter_id: _role_assignment_exists(filter_id, semester_code),
    )


def _course_filter(filter_list: SearchFilterList | None, *, include_mode: bool):
    return _related_filter(
        filter_list,
        include_mode=include_mode,
        build_exists=lambda filter_id: exists(
            select(1)
            .select_from(historie_kurs)
            .where(historie_kurs.c.id_personal == personal.c.id)
            .where(historie_kurs.c.id_kurs == filter_id)
        ),
    )


def _related_filter(filter_list: SearchFilterList | None, *, include_mode: bool, build_exists):
    if filter_list is None or not filter_list.ids:
        return None
    clauses = [build_exists(filter_id) for filter_id in filter_list.ids]
    match_clause = and_(*clauses) if filter_list.conjunction else or_(*clauses)
    return match_clause if include_mode else not_(match_clause)


def _role_assignment_exists(group_id: int, semester_code: int | None):
    stmt = (
        select(1)
        .select_from(historie)
        .where(historie.c.id_personal == personal.c.id)
        .where(historie.c.id_gruppe == group_id)
    )
    if semester_code is not None:
        stmt = stmt.where(historie.c.semester == semester_code)
    return exists(stmt)


def _pingvin_points_subquery():
    return (
        select(
            historie.c.id_personal.label("id_personal"),
            func.coalesce(func.sum(verv.c.pingvinpoeng), 0).label("pingvin_points"),
        )
        .select_from(historie.outerjoin(verv, verv.c.id == historie.c.id_verv))
        .group_by(historie.c.id_personal)
        .subquery()
    )


def _last_semester_subquery():
    return (
        select(
            historie.c.id_personal.label("id_personal"),
            func.max(historie.c.semester).label("last_semester"),
        )
        .group_by(historie.c.id_personal)
        .subquery()
    )


def _get_current_semester_code(today: date | None = None) -> int:
    current = today or date.today()
    season = 1 if current.month < 7 else 2
    return current.year * 10 + season
