from __future__ import annotations

from sqlalchemy.dialects import postgresql

from app.domain.search.models import SearchQuery
from app.domain.search.repository import _build_filters, _pingvin_points_subquery
from app.domain.volunteers.repository import _build_volunteer_search_stmt


def test_build_filters_can_require_current_signed_contract() -> None:
    points = _pingvin_points_subquery()

    filters = _build_filters(SearchQuery(has_active_signed_contract=True), points)

    compiled = str(
        filters[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "historie.signert_kontrakt IS true" in compiled
    assert "historie.semester =" in compiled


def test_volunteer_search_stmt_includes_group_role_and_email_matching() -> None:
    stmt = _build_volunteer_search_stmt(normalized_query="bar", limit=20, offset=0)

    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "string_agg(distinct(public.grupper.navn)" in compiled
    assert "string_agg(distinct(public.verv.verv)" in compiled
    assert "public.personal.epost" in compiled
    assert "anon_3.group_names" in compiled
    assert "anon_3.role_names" in compiled
    assert "public.historie.signert_kontrakt IS true" not in compiled
    assert "public.historie.semester =" not in compiled


def test_volunteer_search_stmt_can_require_active_signed_contract() -> None:
    stmt = _build_volunteer_search_stmt(normalized_query="bar", limit=20, offset=0, only_active=True)

    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "public.historie.signert_kontrakt IS true" in compiled
    assert "public.historie.semester =" in compiled
