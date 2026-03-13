from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from app.db.repository import SqlAlchemyRepository
from app.db.tables import historie, verv
from app.errors import NotConfiguredError
from app.postgrest import PostgrestClient
from app.services.common import coerce_date
from app.services.search_models import SearchCourseFact, SearchMembershipFact, SearchPersonBase


class DatabaseSearchRepository(SqlAlchemyRepository):
    def __init__(self, postgrest_client: PostgrestClient | None = None) -> None:
        super().__init__()
        self.postgrest_client = postgrest_client

    async def search_people_by_birth_date_range(
        self,
        birth_date_after: date | None,
        birth_date_before: date | None,
    ) -> list[SearchPersonBase]:
        rows = await self._select_people(
            filters=_build_birth_date_filters(birth_date_after, birth_date_before),
            order="id.asc",
            limit=500,
        )
        return [_map_search_person(row) for row in rows]

    async def get_group_history_for_people(
        self,
        person_ids: set[int],
        semester_code: int | None = None,
    ) -> list[SearchMembershipFact]:
        if not person_ids:
            return []
        filters: dict[str, str] = {"id_personal": _postgrest_in_filter(person_ids)}
        if semester_code is not None:
            filters["semester"] = f"eq.{semester_code}"
        rows = await self._select_rows(
            "historie",
            select="id_personal,id_gruppe,semester",
            filters=filters,
        )
        return [
            SearchMembershipFact(
                person_id=row["id_personal"],
                group_id=row["id_gruppe"],
                semester_code=row["semester"],
            )
            for row in rows
        ]

    async def get_course_history_for_people(self, person_ids: set[int]) -> list[SearchCourseFact]:
        if not person_ids:
            return []
        rows = await self._select_rows(
            "historie_kurs",
            select="id_personal,id_kurs",
            filters={"id_personal": _postgrest_in_filter(person_ids)},
        )
        return [
            SearchCourseFact(
                person_id=row["id_personal"],
                course_id=row["id_kurs"],
            )
            for row in rows
        ]

    async def get_pingvin_points(self, person_ids: set[int]) -> dict[int, int]:
        if not person_ids:
            return {}
        stmt = (
            select(
                historie.c.id_personal,
                func.coalesce(func.sum(verv.c.pingvinpoeng), 0).label("pingvin_points"),
            )
            .select_from(historie.outerjoin(verv, verv.c.id == historie.c.id_verv))
            .where(historie.c.id_personal.in_(list(person_ids)))
            .group_by(historie.c.id_personal)
        )
        rows = await self.fetch_all_mappings(stmt)
        return {row["id_personal"]: int(row["pingvin_points"] or 0) for row in rows}

    async def get_last_semesters(self, person_ids: set[int]) -> dict[int, int]:
        if not person_ids:
            return {}
        stmt = (
            select(historie.c.id_personal, func.max(historie.c.semester).label("last_semester"))
            .where(historie.c.id_personal.in_(list(person_ids)))
            .group_by(historie.c.id_personal)
        )
        rows = await self.fetch_all_mappings(stmt)
        return {row["id_personal"]: int(row["last_semester"]) for row in rows if row["last_semester"] is not None}

    async def get_people_by_ids(self, person_ids: set[int]) -> list[SearchPersonBase]:
        if not person_ids:
            return []
        rows = await self._select_people(filters={"id": _postgrest_in_filter(person_ids)})
        return [_map_search_person(row) for row in rows]

    async def _select_people(self, *, filters: dict[str, str], order: str | None = None, limit: int | None = None):
        return await self._select_rows(
            "personal",
            select="id,fornavn,etternavn,fodselsdato,telefon,epost",
            filters=filters,
            order=order,
            limit=limit,
        )

    async def _select_rows(
        self,
        table: str,
        *,
        select: str,
        filters: dict[str, str],
        order: str | None = None,
        limit: int | None = None,
    ):
        client = self._require_postgrest_client()
        return await client.select_rows(table, select=select, filters=filters, order=order, limit=limit)

    def _require_postgrest_client(self) -> PostgrestClient:
        if self.postgrest_client is None:
            raise NotConfiguredError("PostgREST-backed search reads are not configured yet.")
        return self.postgrest_client


def _build_birth_date_filters(
    birth_date_after: date | None,
    birth_date_before: date | None,
) -> dict[str, str]:
    filters: dict[str, str] = {}
    if birth_date_after is not None and birth_date_before is not None:
        filters["and"] = (
            f"(fodselsdato.gte.{birth_date_after.isoformat()},"
            f"fodselsdato.lte.{birth_date_before.isoformat()})"
        )
        return filters
    if birth_date_after is not None:
        filters["fodselsdato"] = f"gte.{birth_date_after.isoformat()}"
    if birth_date_before is not None:
        filters["fodselsdato"] = f"lte.{birth_date_before.isoformat()}"
    return filters


def _postgrest_in_filter(person_ids: set[int]) -> str:
    return f"in.({','.join(str(person_id) for person_id in person_ids)})"


def _map_search_person(row: dict) -> SearchPersonBase:
    return SearchPersonBase(
        person_id=row["id"],
        first_name=row.get("fornavn"),
        last_name=row["etternavn"],
        birth_date=coerce_date(row.get("fodselsdato")),
        phone=row.get("telefon"),
        email=row.get("epost"),
    )
