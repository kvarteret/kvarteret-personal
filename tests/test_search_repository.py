from __future__ import annotations

from sqlalchemy.dialects import postgresql

from app.services.search_models import SearchQuery
from app.services.search_repository import _build_filters, _pingvin_points_subquery


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
