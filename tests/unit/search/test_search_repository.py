from __future__ import annotations

from sqlalchemy.dialects import postgresql

from app.domain.search.models import SearchQuery
from app.domain.search.repository import _build_filters, _pingvin_points_subquery
from app.domain.volunteers.search_sql import build_volunteer_search_stmt


def test_build_filters_can_require_current_signed_contract() -> None:
    points = _pingvin_points_subquery()

    filters = _build_filters(SearchQuery(has_active_signed_contract=True), points)

    compiled = str(
        filters[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "role_assignments.contract_signed IS true" in compiled
    assert "role_assignments.semester =" in compiled
    assert "volunteer_application_invites.status = 'not_volunteer'" in compiled


def test_volunteer_search_stmt_includes_group_role_and_email_matching() -> None:
    stmt = build_volunteer_search_stmt(normalized_query="bar", limit=20, offset=0)

    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "lower(public.groups.name) LIKE '%%' || 'bar' || '%%'" in compiled
    assert "lower(public.assignment_roles.name) LIKE '%%' || 'bar' || '%%'" in compiled
    assert "public.volunteer_records.email" in compiled
    # Group/role names match in one pass over matching assignments, not by
    # aggregating every volunteer's assignment names into a string.
    assert "bool_or((lower(public.groups.name) LIKE" in compiled
    assert "assignment_name_matches.group_0" in compiled
    assert "string_agg" not in compiled
    assert "public.role_assignments.contract_signed IS true" not in compiled
    assert "public.role_assignments.semester =" not in compiled


def test_volunteer_search_stmt_can_require_active_signed_contract() -> None:
    stmt = build_volunteer_search_stmt(normalized_query="bar", limit=20, offset=0, only_active=True)

    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "public.role_assignments.contract_signed IS true" in compiled
    assert "public.role_assignments.semester =" in compiled
    assert "public.volunteer_application_invites.status = 'not_volunteer'" in compiled


def test_volunteer_search_stmt_can_carry_the_total_match_count() -> None:
    stmt = build_volunteer_search_stmt(
        normalized_query="bar", limit=20, offset=0, with_total=True
    )

    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "count(*) OVER () AS total_count" in compiled
