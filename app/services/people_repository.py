from __future__ import annotations

from typing import Any

from sqlalchemy import Float, Text, and_, case, delete, exists, func, insert, literal, or_, select, union_all, update

from app.db.repository import SqlAlchemyRepository
from app.db.tables import grupper, historie, paarorende, personal, personal_bilde, personal_fil, personal_kort, verv


class PeopleRepository(SqlAlchemyRepository):
    async def list_people_page(
        self,
        *,
        limit: int,
        after_last_name: str | None = None,
        after_first_name: str | None = None,
        after_person_id: int | None = None,
    ) -> list[dict[str, Any]]:
        name_sort = _name_sort_columns()
        stmt = (
            _people_list_base_stmt()
            .order_by(name_sort.last_name.asc(), name_sort.first_name.asc(), personal.c.id.asc())
            .limit(limit)
        )
        if after_person_id is not None and after_last_name is not None and after_first_name is not None:
            stmt = stmt.where(
                or_(
                    name_sort.last_name > after_last_name,
                    and_(
                        name_sort.last_name == after_last_name,
                        name_sort.first_name > after_first_name,
                    ),
                    and_(
                        name_sort.last_name == after_last_name,
                        name_sort.first_name == after_first_name,
                        personal.c.id > after_person_id,
                    ),
                )
            )
        return await self.fetch_all_mappings(stmt)

    async def search_people_page(self, *, normalized_query: str, limit: int, offset: int = 0) -> list[dict[str, Any]]:
        search = _search_columns()
        tokens = normalized_query.split()
        token_filters = [
            or_(
                search.full_name.contains(token),
                search.first_name.contains(token),
                search.last_name.contains(token),
                search.email.contains(token),
                search.phone.contains(token),
                func.word_similarity(search.full_name, token) >= 0.55,
                func.similarity(search.first_name, token) >= 0.40,
                func.similarity(search.last_name, token) >= 0.40,
                func.similarity(search.email, token) >= 0.45,
                func.similarity(search.phone, token) >= 0.85,
            )
            for token in tokens
        ]

        rank_score = literal(0.0, type_=Float())
        rank_score = rank_score + case((search.full_name == normalized_query, 100.0), else_=0.0)
        rank_score = rank_score + case((search.last_name == normalized_query, 45.0), else_=0.0)
        rank_score = rank_score + case((search.first_name == normalized_query, 35.0), else_=0.0)
        rank_score = rank_score + case((search.full_name.startswith(normalized_query), 28.0), else_=0.0)
        rank_score = rank_score + case((search.full_name.contains(normalized_query), 16.0), else_=0.0)
        rank_score = rank_score + case((search.email.contains(normalized_query), 10.0), else_=0.0)
        rank_score = rank_score + case((search.phone.contains(normalized_query), 10.0), else_=0.0)
        rank_score = rank_score + (
            func.greatest(
                func.word_similarity(search.full_name, normalized_query),
                func.similarity(search.full_name, normalized_query),
                func.similarity(search.first_name, normalized_query),
                func.similarity(search.last_name, normalized_query),
                func.similarity(search.email, normalized_query),
                func.similarity(search.phone, normalized_query),
            )
            * 20.0
        )

        for token in tokens:
            rank_score = rank_score + case((search.full_name.contains(token), 4.0), else_=0.0)
            rank_score = rank_score + case((search.first_name.startswith(token), 5.0), else_=0.0)
            rank_score = rank_score + case((search.last_name.startswith(token), 6.0), else_=0.0)
            rank_score = rank_score + case((search.email.contains(token), 2.5), else_=0.0)

        stmt = (
            _people_list_base_stmt(rank_score=rank_score.label("rank_score"))
            .where(and_(*token_filters))
            .order_by(
                rank_score.desc(),
                personal.c.etternavn.asc(),
                func.coalesce(personal.c.fornavn, "").asc(),
                personal.c.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return await self.fetch_all_mappings(stmt)

    async def fetch_person_shell_row(self, person_id: int) -> dict[str, Any] | None:
        stmt = (
            select(
                personal.c.id,
                personal.c.fornavn,
                personal.c.etternavn,
                personal.c.epost,
                personal.c.telefon,
                personal.c.fodselsdato,
                personal.c.opprettet,
                personal.c.kjonn,
                personal.c.gateadresse,
                personal.c.postnummerid,
                personal.c.arb_status,
                personal_bilde.c.sha1,
                personal_bilde.c.filetype,
            )
            .select_from(personal.outerjoin(personal_bilde, personal_bilde.c.id_personal == personal.c.id))
            .where(personal.c.id == person_id)
            .limit(1)
        )
        return await self.fetch_first_mapping(stmt)

    async def fetch_person_history_rows(self, person_id: int, *, limit: int = 12) -> list[dict[str, Any]]:
        stmt = (
            select(
                historie.c.id,
                historie.c.id_gruppe,
                historie.c.id_verv,
                historie.c.semester,
                historie.c.signert_kontrakt,
                grupper.c.navn.label("group_name"),
                verv.c.verv.label("role_name"),
            )
            .select_from(
                historie.join(grupper, grupper.c.id == historie.c.id_gruppe).outerjoin(verv, verv.c.id == historie.c.id_verv)
            )
            .where(historie.c.id_personal == person_id)
            .order_by(historie.c.semester.desc(), historie.c.id.desc())
            .limit(limit)
        )
        return await self.fetch_all_mappings(stmt)

    async def fetch_person_document_rows(self, person_id: int) -> list[dict[str, Any]]:
        stmt = (
            select(
                personal_fil.c.id,
                personal_fil.c.filename,
                personal_fil.c.filetype,
                personal_fil.c.gruppekobling,
                personal_fil.c.opprettet,
            )
            .where(personal_fil.c.id_personal == person_id)
            .order_by(personal_fil.c.opprettet.desc(), personal_fil.c.id.desc())
        )
        return await self.fetch_all_mappings(stmt)

    async def fetch_person_relation_rows(self, person_id: int) -> list[dict[str, Any]]:
        kin_stmt = (
            select(
                literal("kin").label("relation_type"),
                paarorende.c.id.label("relation_id"),
                paarorende.c.navn.label("primary_text"),
                paarorende.c.telefon.label("secondary_text"),
                paarorende.c.opprettet.label("created_at"),
            )
            .where(paarorende.c.id_personal == person_id)
        )
        card_stmt = (
            select(
                literal("card").label("relation_type"),
                personal_kort.c.id.label("relation_id"),
                personal_kort.c.kortnummer.label("primary_text"),
                literal(None, type_=Text()).label("secondary_text"),
                personal_kort.c.opprettet.label("created_at"),
            )
            .where(personal_kort.c.id_personal == person_id)
        )
        relations = union_all(kin_stmt, card_stmt).subquery()
        stmt = (
            select(
                relations.c.relation_type,
                relations.c.relation_id,
                relations.c.primary_text,
                relations.c.secondary_text,
                relations.c.created_at,
            )
            .order_by(relations.c.created_at.desc(), relations.c.relation_id.desc())
        )
        return await self.fetch_all_mappings(stmt)

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


class _SearchColumns:
    def __init__(self) -> None:
        self.first_name = func.lower(func.coalesce(personal.c.fornavn, ""))
        self.last_name = func.lower(func.coalesce(personal.c.etternavn, ""))
        self.full_name = func.lower(func.concat_ws(" ", func.coalesce(personal.c.fornavn, ""), personal.c.etternavn))
        self.email = func.lower(func.coalesce(personal.c.epost, ""))
        self.phone = func.lower(func.coalesce(personal.c.telefon, ""))


class _NameSortColumns:
    def __init__(self) -> None:
        self.last_name = func.coalesce(personal.c.etternavn, "")
        self.first_name = func.coalesce(personal.c.fornavn, "")


def _search_columns() -> _SearchColumns:
    return _SearchColumns()


def _name_sort_columns() -> _NameSortColumns:
    return _NameSortColumns()


def _people_list_base_stmt(*, rank_score=None):
    points = _pingvin_points_subquery()
    last_semester = _last_semester_subquery()
    columns = [
        personal.c.id,
        personal.c.fornavn,
        personal.c.etternavn,
        personal.c.epost,
        personal.c.telefon,
        personal_bilde.c.sha1,
        personal_bilde.c.filetype,
        last_semester.c.last_semester,
        func.coalesce(points.c.pingvin_points, 0).label("pingvin_points"),
    ]
    if rank_score is not None:
        columns.append(rank_score)
    return select(*columns).select_from(
        personal.outerjoin(personal_bilde, personal_bilde.c.id_personal == personal.c.id)
        .outerjoin(points, points.c.id_personal == personal.c.id)
        .outerjoin(last_semester, last_semester.c.id_personal == personal.c.id)
    )


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
