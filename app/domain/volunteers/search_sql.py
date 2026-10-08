"""SQL builders for the volunteer list and free-text search.

Pure statement construction — no I/O. The ranking expression mirrors the
admin UI's expectations: exact and prefix name matches dominate, then
group/role/contact matches, then trigram similarity as the fuzzy floor.
"""

from __future__ import annotations

from sqlalchemy import (
    Float,
    and_,
    case,
    func,
    literal,
    or_,
    select,
    union,
)

from app.domain.groups.tables import groups
from app.domain.role_assignments.tables import assignment_roles, role_assignments
from app.domain.volunteer_applications.tables import volunteer_application_invites
from app.domain.volunteers.tables import volunteer_photos, volunteer_records
from app.shared.semester import get_current_semester_code


class _SearchColumns:
    def __init__(self) -> None:
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


class _NameSortColumns:
    def __init__(self) -> None:
        self.last_name = func.coalesce(volunteer_records.c.last_name, "")
        self.first_name = func.coalesce(volunteer_records.c.first_name, "")


def search_columns() -> _SearchColumns:
    return _SearchColumns()


def name_sort_columns() -> _NameSortColumns:
    return _NameSortColumns()


def volunteer_list_base_stmt(
    *, rank_score=None, active_volunteers=None, with_total: bool = False
):
    # Points and last semester are correlated per row rather than aggregated
    # over every assignment and joined: Postgres evaluates output expressions
    # after ORDER BY/LIMIT, so only the rows on the page pay for them.
    columns = [
        volunteer_records.c.id,
        volunteer_records.c.first_name,
        volunteer_records.c.last_name,
        volunteer_records.c.email,
        volunteer_records.c.phone,
        volunteer_photos.c.sha1,
        volunteer_photos.c.filetype,
        _last_semester_for_row().label("last_semester"),
        func.coalesce(_pingvin_points_for_row(), 0).label("pingvin_points"),
    ]
    if rank_score is not None:
        columns.append(rank_score)
    if with_total:
        # Total matches before LIMIT, so the first page needs no count query.
        columns.append(func.count().over().label("total_count"))
    base_from = volunteer_records
    if active_volunteers is not None:
        base_from = base_from.join(
            active_volunteers, active_volunteers.c.volunteer_id == volunteer_records.c.id
        )
    return select(*columns).select_from(
        base_from.outerjoin(
            volunteer_photos, volunteer_photos.c.volunteer_id == volunteer_records.c.id
        )
    )


def _pingvin_points_for_row():
    return (
        select(func.sum(assignment_roles.c.penguin_points))
        .select_from(
            role_assignments.outerjoin(
                assignment_roles, assignment_roles.c.id == role_assignments.c.role_id
            )
        )
        .where(role_assignments.c.volunteer_id == volunteer_records.c.id)
        .scalar_subquery()
    )


def _last_semester_for_row():
    return (
        select(func.max(role_assignments.c.semester))
        .where(role_assignments.c.volunteer_id == volunteer_records.c.id)
        .scalar_subquery()
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


def current_active_volunteers_subquery(*, semester_code: int | None = None):
    semester_code = (
        get_current_semester_code() if semester_code is None else semester_code
    )
    active_trial = (
        select(volunteer_application_invites.c.id)
        .where(
            volunteer_application_invites.c.promoted_volunteer_id
            == role_assignments.c.volunteer_id,
            volunteer_application_invites.c.status == "trial",
            volunteer_application_invites.c.trial_ends_at > func.now(),
        )
        .exists()
    )
    assigned_volunteers = (
        select(role_assignments.c.volunteer_id.label("volunteer_id"))
        .where(role_assignments.c.semester == semester_code)
        .where(or_(role_assignments.c.contract_signed.is_(True), active_trial))
        .where(
            ~select(volunteer_application_invites.c.id)
            .where(
                volunteer_application_invites.c.promoted_volunteer_id
                == role_assignments.c.volunteer_id
            )
            .where(volunteer_application_invites.c.status == "not_volunteer")
            .exists()
        )
        .group_by(role_assignments.c.volunteer_id)
    )
    trial_volunteers = select(
        volunteer_application_invites.c.promoted_volunteer_id.label("volunteer_id")
    ).where(
        volunteer_application_invites.c.status == "trial",
        volunteer_application_invites.c.trial_ends_at > func.now(),
        volunteer_application_invites.c.promoted_volunteer_id.is_not(None),
    )
    return union(assigned_volunteers, trial_volunteers).subquery()


class _AssignmentNameMatches:
    """Per-volunteer flags for "holds a group/role whose name contains X".

    One pass over only the assignments whose group or role name matches some
    search needle, grouped per volunteer, replaces aggregating every
    volunteer's assignment names into a string and pattern-matching that.
    """

    def __init__(self, needles: list[str], *, only_current_semester: bool) -> None:
        self._index = {needle: i for i, needle in enumerate(dict.fromkeys(needles))}
        group_name = func.lower(groups.c.name)
        role_name = func.lower(assignment_roles.c.name)
        flags = []
        likes = []
        for needle, i in self._index.items():
            group_like = group_name.contains(needle)
            role_like = role_name.contains(needle)
            flags.append(func.bool_or(group_like).label(f"group_{i}"))
            flags.append(func.bool_or(role_like).label(f"role_{i}"))
            likes.extend([group_like, role_like])
        matches = (
            select(role_assignments.c.volunteer_id.label("volunteer_id"), *flags)
            .select_from(
                role_assignments.outerjoin(
                    groups, groups.c.id == role_assignments.c.group_id
                ).outerjoin(
                    assignment_roles,
                    assignment_roles.c.id == role_assignments.c.role_id,
                )
            )
            .where(or_(*likes))
            .group_by(role_assignments.c.volunteer_id)
        )
        if only_current_semester:
            matches = matches.where(
                role_assignments.c.semester == get_current_semester_code()
            ).where(role_assignments.c.contract_signed.is_(True))
        self.subquery = matches.subquery("assignment_name_matches")

    def join_onto(self, stmt):
        return stmt.outerjoin(
            self.subquery, self.subquery.c.volunteer_id == volunteer_records.c.id
        )

    def group(self, needle: str):
        return func.coalesce(self.subquery.c[f"group_{self._index[needle]}"], False)

    def role(self, needle: str):
        return func.coalesce(self.subquery.c[f"role_{self._index[needle]}"], False)


def _search_token_filters(search, tokens, name_matches: _AssignmentNameMatches):
    return [
        or_(
            search.full_name.contains(token),
            search.first_name.contains(token),
            search.last_name.contains(token),
            search.email.contains(token),
            search.phone.contains(token),
            name_matches.group(token),
            name_matches.role(token),
            func.word_similarity(search.full_name, token) >= 0.55,
            func.similarity(search.first_name, token) >= 0.40,
            func.similarity(search.last_name, token) >= 0.40,
        )
        for token in tokens
    ]


def build_volunteer_search_stmt(
    *,
    normalized_query: str,
    limit: int,
    offset: int,
    only_active: bool = False,
    with_total: bool = False,
):
    active_volunteers = current_active_volunteers_subquery() if only_active else None
    search = search_columns()
    tokens = normalized_query.split()
    name_matches = _AssignmentNameMatches(
        [normalized_query, *tokens], only_current_semester=only_active
    )
    token_filters = _search_token_filters(search, tokens, name_matches)
    group_match = name_matches.group
    role_match = name_matches.role

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
        (group_match(normalized_query), 14.0), else_=0.0
    )
    rank_score = rank_score + case(
        (role_match(normalized_query), 14.0), else_=0.0
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
            (group_match(token), 3.0), else_=0.0
        )
        rank_score = rank_score + case(
            (role_match(token), 3.0), else_=0.0
        )
        rank_score = rank_score + case((search.email.contains(token), 2.5), else_=0.0)

    stmt = (
        name_matches.join_onto(
            volunteer_list_base_stmt(
                rank_score=rank_score.label("rank_score"),
                active_volunteers=active_volunteers,
                with_total=with_total,
            )
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
    active_volunteers = current_active_volunteers_subquery() if only_active else None
    tokens = normalized_query.split()
    name_matches = _AssignmentNameMatches(tokens, only_current_semester=only_active)
    token_filters = _search_token_filters(search_columns(), tokens, name_matches)
    matching = (
        name_matches.join_onto(
            select(volunteer_records.c.id).select_from(
                volunteer_records
                if active_volunteers is None
                else volunteer_records.join(
                    active_volunteers,
                    active_volunteers.c.volunteer_id == volunteer_records.c.id,
                )
            )
        )
        .where(and_(*token_filters))
        .subquery()
    )
    return select(func.count()).select_from(matching)
