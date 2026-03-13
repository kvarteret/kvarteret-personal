from __future__ import annotations

from typing import Any

from sqlalchemy import Float, and_, case, delete, exists, func, insert, literal, or_, select, update

from app.db.repository import SqlAlchemyRepository
from app.db.tables import historie, personal, personal_bilde, personal_fil, verv
from app.errors import NotConfiguredError
from app.postgrest import PostgrestClient


class PeopleRepository(SqlAlchemyRepository):
    def __init__(self, postgrest_client: PostgrestClient | None = None) -> None:
        super().__init__()
        self.postgrest_client = postgrest_client

    async def list_people_page(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        stmt = (
            select(
                personal.c.id,
                personal.c.fornavn,
                personal.c.etternavn,
                personal.c.epost,
                personal.c.telefon,
                personal.c.fodselsdato,
                personal.c.opprettet,
                personal_bilde.c.sha1,
                personal_bilde.c.filetype,
                _last_semester_subquery().label("last_semester"),
                _pingvin_points_subquery().label("pingvin_points"),
            )
            .select_from(personal.outerjoin(personal_bilde, personal_bilde.c.id_personal == personal.c.id))
            .order_by(personal.c.etternavn.asc(), personal.c.fornavn.asc(), personal.c.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return await self.fetch_all_mappings(stmt)

    async def search_people_page(self, *, normalized_query: str, limit: int, offset: int):
        full_name_search = _searchable_full_name_expr()
        first_name_search = _searchable_field_expr(personal.c.fornavn)
        last_name_search = _searchable_field_expr(personal.c.etternavn)
        email_search = _searchable_field_expr(personal.c.epost)
        phone_search = _searchable_field_expr(personal.c.telefon)

        tokens = normalized_query.split()
        token_filters = [
            or_(
                full_name_search.contains(token),
                first_name_search.contains(token),
                last_name_search.contains(token),
                email_search.contains(token),
                phone_search.contains(token),
                func.word_similarity(full_name_search, token) >= 0.55,
                func.similarity(first_name_search, token) >= 0.40,
                func.similarity(last_name_search, token) >= 0.40,
                func.similarity(email_search, token) >= 0.45,
                func.similarity(phone_search, token) >= 0.85,
            )
            for token in tokens
        ]

        rank_score = literal(0.0, type_=Float())
        rank_score = rank_score + case((full_name_search == normalized_query, 100.0), else_=0.0)
        rank_score = rank_score + case((last_name_search == normalized_query, 45.0), else_=0.0)
        rank_score = rank_score + case((first_name_search == normalized_query, 35.0), else_=0.0)
        rank_score = rank_score + case((full_name_search.startswith(normalized_query), 28.0), else_=0.0)
        rank_score = rank_score + case((full_name_search.contains(normalized_query), 16.0), else_=0.0)
        rank_score = rank_score + case((email_search.contains(normalized_query), 10.0), else_=0.0)
        rank_score = rank_score + case((phone_search.contains(normalized_query), 10.0), else_=0.0)
        rank_score = rank_score + (
            func.greatest(
                func.word_similarity(full_name_search, normalized_query),
                func.similarity(full_name_search, normalized_query),
                func.similarity(first_name_search, normalized_query),
                func.similarity(last_name_search, normalized_query),
                func.similarity(email_search, normalized_query),
                func.similarity(phone_search, normalized_query),
            )
            * 20.0
        )

        for token in tokens:
            rank_score = rank_score + case((full_name_search.contains(token), 4.0), else_=0.0)
            rank_score = rank_score + case((first_name_search.startswith(token), 5.0), else_=0.0)
            rank_score = rank_score + case((last_name_search.startswith(token), 6.0), else_=0.0)
            rank_score = rank_score + case((email_search.contains(token), 2.5), else_=0.0)

        stmt = (
            select(
                personal.c.id,
                personal.c.fornavn,
                personal.c.etternavn,
                personal.c.epost,
                personal.c.telefon,
                personal.c.fodselsdato,
                personal.c.opprettet,
                personal_bilde.c.sha1,
                personal_bilde.c.filetype,
                _last_semester_subquery().label("last_semester"),
                _pingvin_points_subquery().label("pingvin_points"),
                rank_score.label("rank_score"),
            )
            .select_from(personal.outerjoin(personal_bilde, personal_bilde.c.id_personal == personal.c.id))
            .where(and_(*token_filters))
            .order_by(rank_score.desc(), personal.c.etternavn.asc(), personal.c.fornavn.asc(), personal.c.id.asc())
            .limit(limit)
            .offset(offset)
        )

        return await self.fetch_all_mappings(stmt)

    async def fetch_person_detail_row(self, person_id: int) -> dict[str, Any] | None:
        if self.postgrest_client is None:
            raise NotConfiguredError("PostgREST-backed people reads are not configured yet.")
        rows = await self.postgrest_client.select_rows(
            "personal",
            select=(
                "id,fornavn,etternavn,epost,telefon,fodselsdato,opprettet,kjonn,"
                "gateadresse,postnummerid,arb_status,"
                "personal_bilde(sha1,filetype),"
                "paarorende(id,navn,telefon,opprettet),"
                "personal_kort(id,kortnummer,opprettet),"
                "personal_fil(id,filename,filetype,gruppekobling,opprettet),"
                "historie(id,id_gruppe,id_verv,semester,signert_kontrakt,grupper(navn),verv(id,verv))"
            ),
            filters={"id": f"eq.{person_id}"},
            limit=1,
        )
        return rows[0] if rows else None

    async def person_exists(self, person_id: int) -> bool:
        return bool(await self.fetch_scalar(select(exists().where(personal.c.id == person_id))))

    async def fetch_photo_record(self, person_id: int):
        return await self.fetch_first_mapping(
            select(personal_bilde.c.sha1, personal_bilde.c.filetype)
            .where(personal_bilde.c.id_personal == person_id)
            .limit(1)
        )

    async def save_photo_record(self, *, person_id: int, filename_hash: str, extension: str, existing: bool) -> None:
        async def save(session):
            if existing:
                await session.execute(
                    update(personal_bilde)
                    .where(personal_bilde.c.id_personal == person_id)
                    .values(filetype=extension)
                )
            else:
                await session.execute(
                    insert(personal_bilde).values(id_personal=person_id, sha1=filename_hash, filetype=extension)
                )

        await self.execute_in_transaction(save)

    async def delete_photo_record(self, person_id: int) -> None:
        await self.execute(delete(personal_bilde).where(personal_bilde.c.id_personal == person_id))

    async def document_exists(self, *, person_id: int, filename: str) -> bool:
        return bool(
            await self.fetch_scalar(
                select(
                    exists().where(
                        personal_fil.c.id_personal == person_id,
                        func.lower(personal_fil.c.filename) == filename.lower(),
                    )
                )
            )
        )

    async def create_document_record(
        self,
        *,
        person_id: int,
        group_id: int | None,
        filename: str,
        extension: str,
    ):
        stmt = (
            insert(personal_fil)
            .values(
                id_personal=person_id,
                gruppekobling=group_id,
                filename=filename,
                filetype=extension,
            )
            .returning(
                personal_fil.c.id,
                personal_fil.c.id_personal,
                personal_fil.c.gruppekobling,
                personal_fil.c.filename,
                personal_fil.c.filetype,
            )
        )
        return await self.execute_one_mapping(stmt)

    async def fetch_document_record(self, document_id: int):
        return await self.fetch_first_mapping(
            select(personal_fil.c.id, personal_fil.c.id_personal, personal_fil.c.filename)
            .where(personal_fil.c.id == document_id)
            .limit(1)
        )

    async def delete_document_record(self, document_id: int) -> None:
        await self.execute(delete(personal_fil).where(personal_fil.c.id == document_id))


def _searchable_field_expr(column) -> object:
    return func.lower(func.btrim(func.coalesce(column, "")))


def _searchable_full_name_expr() -> object:
    return func.lower(
        func.btrim(
            func.coalesce(personal.c.fornavn, "")
            + literal(" ")
            + func.coalesce(personal.c.etternavn, "")
        )
    )


def _last_semester_subquery():
    return (
        select(func.max(historie.c.semester))
        .where(historie.c.id_personal == personal.c.id)
        .scalar_subquery()
    )


def _pingvin_points_subquery():
    return (
        select(func.coalesce(func.sum(verv.c.pingvinpoeng), 0))
        .select_from(historie.outerjoin(verv, verv.c.id == historie.c.id_verv))
        .where(historie.c.id_personal == personal.c.id)
        .scalar_subquery()
    )
