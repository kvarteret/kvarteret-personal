"""SQL builders for the volunteer list and free-text search.

Pure statement construction — no I/O. The ranking expression mirrors the
admin UI's expectations: exact and prefix name matches dominate, then
group/role/contact matches, then trigram similarity as the fuzzy floor.
"""

from __future__ import annotations

from sqlalchemy import (
    Float,
    Text,
    and_,
    case,
    func,
    literal,
    or_,
    select,
)

from app.domain.groups.tables import groups
from app.domain.role_assignments.tables import assignment_roles, role_assignments
from app.domain.volunteers.tables import volunteer_photos, volunteer_records
from app.infrastructure.formatting.semester import get_current_semester_code


class _SearchColumns:
    def __init__(self, assignment_search_text=None) -> None:
        self.first_name = func.lower(func.coalesce(volunteer_records.c.first_name, ""))
        self.last_name = func.lower(func.coalesce(volunteer_records.c.last_name, ""))
        self.full_name = func.lower(
            func.concat_ws(
                " ",
                func.coalesce(volunteer_records.c.first_name, ""),
                volunteer_records.c.last_name,
            )
        )
        self.email = func.lower(func.coalesce(volunteer_records.c.email, ""))
        self.phone = func.lower(func.coalesce(volunteer_records.c.phone, ""))
        self.group_names = func.lower(
            func.coalesce(
                assignment_search_text.c.group_names
                if assignment_search_text is not None
                else literal("", type_=Text()),
                "",
            )
        )
        self.role_names = func.lower(
            func.coalesce(
                assignment_search_text.c.role_names
                if assignment_search_text is not None
                else literal("", type_=Text()),
                "",
            )
        )


class _NameSortColumns:
    def __init__(self) -> None:
        self.last_name = func.coalesce(volunteer_records.c.last_name, "")
        self.first_name = func.coalesce(volunteer_records.c.first_name, "")


def search_columns(assignment_search_text=None) -> _SearchColumns:
    return _SearchColumns(assignment_search_text)


def name_sort_columns() -> _NameSortColumns:
    return _NameSortColumns()


def volunteer_list_base_stmt(*, rank_score=None, active_volunteers=None):
    points = pingvin_points_subquery()
    last_semester = _last_semester_subquery()
    columns = [
        volunteer_records.c.id,
        volunteer_records.c.first_name,
        volunteer_records.c.last_name,
        volunteer_records.c.email,
        volunteer_records.c.phone,
        volunteer_photos.c.sha1,
        volunteer_photos.c.filetype,
        last_semester.c.last_semester,
        func.coalesce(points.c.pingvin_points, 0).label("pingvin_points"),
    ]
    if rank_score is not None:
        columns.append(rank_score)
    base_from = volunteer_records
    if active_volunteers is not None:
        base_from = base_from.join(
            active_volunteers, active_volunteers.c.volunteer_id == volunteer_records.c.id
        )
    return select(*columns).select_from(
        base_from.outerjoin(
            volunteer_photos, volunteer_photos.c.volunteer_id == volunteer_records.c.id
        )
        .outerjoin(points, points.c.volunteer_id == volunteer_records.c.id)
        .outerjoin(last_semester, last_semester.c.volunteer_id == volunteer_records.c.id)
    )


def pingvin_points_subquery():
    return (
        select(
            role_assignments.c.volunteer_id.label("volunteer_id"),
            func.coalesce(func.sum(assignment_roles.c.penguin_points), 0).label(
                "pingvin_points"
            ),
        )
        .select_from(
            role_assignments.outerjoin(
                assignment_roles, assignment_roles.c.id == role_assignments.c.role_id
            )
        )
        .group_by(role_assignments.c.volunteer_id)
        .subquery()
    )


def _last_semester_subquery():
    return (
        select(
            role_assignments.c.volunteer_id.label("volunteer_id"),
            func.max(role_assignments.c.semester).label("last_semester"),
        )
        .group_by(role_assignments.c.volunteer_id)
        .subquery()
    )


def current_discount_level_subquery():
    return (
        select(
            role_assignments.c.volunteer_id.label("volunteer_id"),
            func.max(groups.c.discount_tier).label("current_discount_level"),
        )
        .select_from(
            role_assignments.join(groups, groups.c.id == role_assignments.c.group_id)
        )
        .where(role_assignments.c.semester == get_current_semester_code())
        .group_by(role_assignments.c.volunteer_id)
        .subquery()
    )


def current_active_volunteers_subquery():
    return (
        select(role_assignments.c.volunteer_id.label("volunteer_id"))
        .where(role_assignments.c.semester == get_current_semester_code())
        .where(role_assignments.c.contract_signed.is_(True))
        .group_by(role_assignments.c.volunteer_id)
        .subquery()
    )


def _assignment_search_text_subquery(*, only_current_semester: bool = True):
    base = (
        select(
            role_assignments.c.volunteer_id.label("volunteer_id"),
            func.coalesce(
                func.lower(func.string_agg(func.distinct(groups.c.name), literal(" "))),
                "",
            ).label("group_names"),
            func.coalesce(
                func.lower(
                    func.string_agg(
                        func.distinct(assignment_roles.c.name), literal(" ")
                    )
                ),
                "",
            ).label("role_names"),
        )
        .select_from(
            role_assignments.outerjoin(
                groups, groups.c.id == role_assignments.c.group_id
            ).outerjoin(
                assignment_roles,
                assignment_roles.c.id == role_assignments.c.role_id,
            )
        )
        .group_by(role_assignments.c.volunteer_id)
    )
    if only_current_semester:
        base = base.where(
            role_assignments.c.semester == get_current_semester_code()
        ).where(role_assignments.c.contract_signed.is_(True))
    return base.subquery()


def build_volunteer_search_stmt(
    *, normalized_query: str, limit: int, offset: int, only_active: bool = False
):
    assignment_search_text = _assignment_search_text_subquery(
        only_current_semester=only_active
    )
    active_volunteers = current_active_volunteers_subquery() if only_active else None
    search = search_columns(assignment_search_text)
    tokens = normalized_query.split()
    token_filters = [
        or_(
            search.full_name.contains(token),
            search.first_name.contains(token),
            search.last_name.contains(token),
            search.email.contains(token),
            search.phone.contains(token),
            search.group_names.contains(token),
            search.role_names.contains(token),
            func.word_similarity(search.full_name, token) >= 0.55,
            func.similarity(search.first_name, token) >= 0.40,
            func.similarity(search.last_name, token) >= 0.40,
        )
        for token in tokens
    ]

    rank_score = literal(0.0, type_=Float())
    rank_score = rank_score + case(
        (search.full_name == normalized_query, 100.0), else_=0.0
    )
    rank_score = rank_score + case(
        (search.last_name == normalized_query, 45.0), else_=0.0
    )
    rank_score = rank_score + case(
        (search.first_name == normalized_query, 35.0), else_=0.0
    )
    rank_score = rank_score + case(
        (search.full_name.startswith(normalized_query), 28.0), else_=0.0
    )
    rank_score = rank_score + case(
        (search.full_name.contains(normalized_query), 16.0), else_=0.0
    )
    rank_score = rank_score + case(
        (search.group_names.contains(normalized_query), 14.0), else_=0.0
    )
    rank_score = rank_score + case(
        (search.role_names.contains(normalized_query), 14.0), else_=0.0
    )
    rank_score = rank_score + case(
        (search.email.contains(normalized_query), 10.0), else_=0.0
    )
    rank_score = rank_score + case(
        (search.phone.contains(normalized_query), 10.0), else_=0.0
    )
    rank_score = rank_score + (
        func.greatest(
            func.word_similarity(search.full_name, normalized_query),
            func.similarity(search.full_name, normalized_query),
            func.similarity(search.first_name, normalized_query),
            func.similarity(search.last_name, normalized_query),
        )
        * 20.0
    )

    for token in tokens:
        rank_score = rank_score + case(
            (search.full_name.contains(token), 4.0), else_=0.0
        )
        rank_score = rank_score + case(
            (search.first_name.startswith(token), 5.0), else_=0.0
        )
        rank_score = rank_score + case(
            (search.last_name.startswith(token), 6.0), else_=0.0
        )
        rank_score = rank_score + case(
            (search.group_names.contains(token), 3.0), else_=0.0
        )
        rank_score = rank_score + case(
            (search.role_names.contains(token), 3.0), else_=0.0
        )
        rank_score = rank_score + case((search.email.contains(token), 2.5), else_=0.0)

    stmt = (
        volunteer_list_base_stmt(
            rank_score=rank_score.label("rank_score"),
            active_volunteers=active_volunteers,
        )
        .outerjoin(
            assignment_search_text,
            assignment_search_text.c.volunteer_id == volunteer_records.c.id,
        )
        .where(and_(*token_filters))
        .order_by(
            rank_score.desc(),
            volunteer_records.c.last_name.asc(),
            func.coalesce(volunteer_records.c.first_name, "").asc(),
            volunteer_records.c.id.asc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return stmt


def build_volunteer_search_count_stmt(
    *, normalized_query: str, only_active: bool = False
):
    assignment_search_text = _assignment_search_text_subquery(
        only_current_semester=only_active
    )
    active_volunteers = current_active_volunteers_subquery() if only_active else None
    search = search_columns(assignment_search_text)
    tokens = normalized_query.split()
    token_filters = [
        or_(
            search.full_name.contains(token),
            search.first_name.contains(token),
            search.last_name.contains(token),
            search.email.contains(token),
            search.phone.contains(token),
            search.group_names.contains(token),
            search.role_names.contains(token),
            func.word_similarity(search.full_name, token) >= 0.55,
            func.similarity(search.first_name, token) >= 0.40,
            func.similarity(search.last_name, token) >= 0.40,
        )
        for token in tokens
    ]
    subq = (
        select(volunteer_records.c.id)
        .select_from(
            volunteer_records
            if active_volunteers is None
            else volunteer_records.join(
                active_volunteers,
                active_volunteers.c.volunteer_id == volunteer_records.c.id,
            )
        )
        .outerjoin(
            volunteer_photos, volunteer_photos.c.volunteer_id == volunteer_records.c.id
        )
        .outerjoin(
            assignment_search_text,
            assignment_search_text.c.volunteer_id == volunteer_records.c.id,
        )
        .where(and_(*token_filters))
        .subquery()
    )
    return select(func.count()).select_from(subq)
