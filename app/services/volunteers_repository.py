from __future__ import annotations

from typing import Any

from sqlalchemy import Float, Text, and_, case, delete, exists, func, insert, literal, or_, select, union_all, update

from app.db.repository import SqlAlchemyRepository
from app.db.tables import (
    assignment_roles,
    course_completions,
    groups,
    role_assignments,
    volunteer_cards,
    volunteer_documents,
    volunteer_next_of_kin,
    volunteer_photos,
    volunteer_records,
)


class VolunteersRepository(SqlAlchemyRepository):
    async def list_volunteers_page(
        self,
        *,
        limit: int,
        after_last_name: str | None = None,
        after_first_name: str | None = None,
        after_volunteer_id: int | None = None,
    ) -> list[dict[str, Any]]:
        name_sort = _name_sort_columns()
        stmt = (
            _volunteer_list_base_stmt()
            .order_by(name_sort.last_name.asc(), name_sort.first_name.asc(), volunteer_records.c.id.asc())
            .limit(limit)
        )
        if after_volunteer_id is not None and after_last_name is not None and after_first_name is not None:
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
                        volunteer_records.c.id > after_volunteer_id,
                    ),
                )
            )
        return await self.fetch_all_mappings(stmt)

    async def search_volunteers_page(self, *, normalized_query: str, limit: int, offset: int = 0) -> list[dict[str, Any]]:
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
            _volunteer_list_base_stmt(rank_score=rank_score.label("rank_score"))
            .where(and_(*token_filters))
            .order_by(
                rank_score.desc(),
                volunteer_records.c.etternavn.asc(),
                func.coalesce(volunteer_records.c.fornavn, "").asc(),
                volunteer_records.c.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return await self.fetch_all_mappings(stmt)

    async def fetch_volunteer_shell_row(self, volunteer_id: int) -> dict[str, Any] | None:
        points = _pingvin_points_subquery()
        stmt = (
            select(
                volunteer_records.c.id,
                volunteer_records.c.fornavn,
                volunteer_records.c.etternavn,
                volunteer_records.c.epost,
                volunteer_records.c.telefon,
                volunteer_records.c.fodselsdato,
                volunteer_records.c.opprettet,
                volunteer_records.c.kjonn,
                volunteer_records.c.gateadresse,
                volunteer_records.c.postnummerid,
                func.coalesce(points.c.pingvin_points, 0).label("pingvin_points"),
                volunteer_photos.c.sha1,
                volunteer_photos.c.filetype,
            )
            .select_from(
                volunteer_records.outerjoin(
                    volunteer_photos,
                    volunteer_photos.c.id_personal == volunteer_records.c.id,
                ).outerjoin(
                    points,
                    points.c.id_personal == volunteer_records.c.id,
                )
            )
            .where(volunteer_records.c.id == volunteer_id)
            .limit(1)
        )
        return await self.fetch_first_mapping(stmt)

    async def fetch_volunteer_role_assignment_rows(
        self,
        volunteer_id: int,
        *,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(
                role_assignments.c.id,
                role_assignments.c.id_gruppe,
                role_assignments.c.id_verv,
                role_assignments.c.semester,
                role_assignments.c.signert_kontrakt,
                groups.c.navn.label("group_name"),
                assignment_roles.c.verv.label("role_name"),
                assignment_roles.c.pingvinpoeng,
            )
            .select_from(
                role_assignments.join(groups, groups.c.id == role_assignments.c.id_gruppe).outerjoin(
                    assignment_roles,
                    assignment_roles.c.id == role_assignments.c.id_verv,
                )
            )
            .where(role_assignments.c.id_personal == volunteer_id)
            .order_by(role_assignments.c.semester.desc(), role_assignments.c.id.desc())
            .limit(limit)
        )
        return await self.fetch_all_mappings(stmt)

    async def list_assignment_group_rows(self) -> list[dict[str, Any]]:
        stmt = (
            select(groups.c.id, groups.c.navn, groups.c.aktiv)
            .order_by(groups.c.aktiv.desc(), groups.c.navn.asc(), groups.c.id.asc())
        )
        return await self.fetch_all_mappings(stmt)

    async def list_assignment_role_rows(self, group_id: int) -> list[dict[str, Any]]:
        stmt = (
            select(
                assignment_roles.c.id,
                assignment_roles.c.id_gruppe,
                assignment_roles.c.verv,
                assignment_roles.c.pingvinpoeng,
            )
            .where(assignment_roles.c.id_gruppe == group_id)
            .order_by(assignment_roles.c.verv.asc().nullslast(), assignment_roles.c.id.asc())
        )
        return await self.fetch_all_mappings(stmt)

    async def fetch_volunteer_document_rows(self, volunteer_id: int) -> list[dict[str, Any]]:
        stmt = (
            select(
                volunteer_documents.c.id,
                volunteer_documents.c.filename,
                volunteer_documents.c.filetype,
                volunteer_documents.c.gruppekobling,
                volunteer_documents.c.opprettet,
            )
            .where(volunteer_documents.c.id_personal == volunteer_id)
            .order_by(volunteer_documents.c.opprettet.desc(), volunteer_documents.c.id.desc())
        )
        return await self.fetch_all_mappings(stmt)

    async def fetch_volunteer_relation_rows(self, volunteer_id: int) -> list[dict[str, Any]]:
        kin_stmt = (
            select(
                literal("kin").label("relation_type"),
                volunteer_next_of_kin.c.id.label("relation_id"),
                volunteer_next_of_kin.c.navn.label("primary_text"),
                volunteer_next_of_kin.c.telefon.label("secondary_text"),
                volunteer_next_of_kin.c.opprettet.label("created_at"),
            )
            .where(volunteer_next_of_kin.c.id_personal == volunteer_id)
        )
        card_stmt = (
            select(
                literal("card").label("relation_type"),
                volunteer_cards.c.id.label("relation_id"),
                volunteer_cards.c.kortnummer.label("primary_text"),
                literal(None, type_=Text()).label("secondary_text"),
                volunteer_cards.c.opprettet.label("created_at"),
            )
            .where(volunteer_cards.c.id_personal == volunteer_id)
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

    async def volunteer_exists(self, volunteer_id: int) -> bool:
        return bool(await self.fetch_scalar(select(exists().where(volunteer_records.c.id == volunteer_id))))

    async def fetch_photo_record(self, volunteer_id: int):
        return await self.fetch_first_mapping(
            select(volunteer_photos.c.sha1, volunteer_photos.c.filetype)
            .where(volunteer_photos.c.id_personal == volunteer_id)
            .limit(1)
        )

    async def save_photo_record(
        self,
        *,
        volunteer_id: int,
        filename_hash: str,
        extension: str,
        existing: bool,
    ) -> None:
        async def save(session):
            if existing:
                await session.execute(
                    update(volunteer_photos)
                    .where(volunteer_photos.c.id_personal == volunteer_id)
                    .values(filetype=extension)
                )
            else:
                await session.execute(
                    insert(volunteer_photos).values(id_personal=volunteer_id, sha1=filename_hash, filetype=extension)
                )

        await self.execute_in_transaction(save)

    async def update_volunteer_profile(
        self,
        *,
        volunteer_id: int,
        first_name: str | None,
        last_name: str,
        email: str | None,
        phone: str | None,
        birth_date,
        gender_code: str,
        address: str | None,
        postal_code: str | None,
    ) -> None:
        await self.execute(
            update(volunteer_records)
            .where(volunteer_records.c.id == volunteer_id)
            .values(
                fornavn=first_name,
                etternavn=last_name,
                epost=email,
                telefon=phone,
                fodselsdato=birth_date,
                kjonn=gender_code,
                gateadresse=address,
                postnummerid=postal_code,
            )
        )

    async def role_belongs_to_group(self, *, group_id: int, role_id: int) -> bool:
        return bool(
            await self.fetch_scalar(
                select(
                        exists().where(
                        assignment_roles.c.id == role_id,
                        assignment_roles.c.id_gruppe == group_id,
                    )
                )
            )
        )

    async def role_assignment_exists(
        self,
        *,
        volunteer_id: int,
        group_id: int,
        role_id: int,
        semester_code: int,
        exclude_history_id: int | None = None,
    ) -> bool:
        filters = [
            role_assignments.c.id_personal == volunteer_id,
            role_assignments.c.id_gruppe == group_id,
            role_assignments.c.id_verv == role_id,
            role_assignments.c.semester == semester_code,
        ]
        if exclude_history_id is not None:
            filters.append(role_assignments.c.id != exclude_history_id)
        return bool(
            await self.fetch_scalar(
                select(
                    exists().where(
                        *filters,
                    )
                )
            )
        )

    async def create_role_assignment(
        self,
        *,
        volunteer_id: int,
        group_id: int,
        role_id: int,
        semester_code: int,
        contract_signed: bool,
    ) -> None:
        await self.execute(
            insert(role_assignments).values(
                id_personal=volunteer_id,
                id_gruppe=group_id,
                id_verv=role_id,
                semester=semester_code,
                signert_kontrakt=contract_signed,
            )
        )

    async def fetch_role_assignment_record(self, history_id: int):
        return await self.fetch_first_mapping(
            select(
                role_assignments.c.id,
                role_assignments.c.id_personal,
                role_assignments.c.id_gruppe,
                role_assignments.c.id_verv,
                role_assignments.c.semester,
                role_assignments.c.signert_kontrakt,
            )
            .where(role_assignments.c.id == history_id)
            .limit(1)
        )

    async def update_role_assignment(
        self,
        history_id: int,
        *,
        group_id: int,
        role_id: int,
        semester_code: int,
        contract_signed: bool,
    ) -> None:
        await self.execute(
            update(role_assignments)
            .where(role_assignments.c.id == history_id)
            .values(
                id_gruppe=group_id,
                id_verv=role_id,
                semester=semester_code,
                signert_kontrakt=contract_signed,
            )
        )

    async def delete_role_assignment(self, history_id: int) -> None:
        await self.execute(delete(role_assignments).where(role_assignments.c.id == history_id))

    async def delete_photo_record(self, volunteer_id: int) -> None:
        await self.execute(delete(volunteer_photos).where(volunteer_photos.c.id_personal == volunteer_id))

    async def document_exists(self, *, volunteer_id: int, filename: str) -> bool:
        return bool(
            await self.fetch_scalar(
                select(
                    exists().where(
                        volunteer_documents.c.id_personal == volunteer_id,
                        func.lower(volunteer_documents.c.filename) == filename.lower(),
                    )
                )
            )
        )

    async def create_document_record(
        self,
        *,
        volunteer_id: int,
        group_id: int | None,
        filename: str,
        extension: str,
    ):
        stmt = (
            insert(volunteer_documents)
            .values(
                id_personal=volunteer_id,
                gruppekobling=group_id,
                filename=filename,
                filetype=extension,
            )
            .returning(
                volunteer_documents.c.id,
                volunteer_documents.c.id_personal,
                volunteer_documents.c.gruppekobling,
                volunteer_documents.c.filename,
                volunteer_documents.c.filetype,
            )
        )
        return await self.execute_one_mapping(stmt)

    async def fetch_document_record(self, document_id: int):
        return await self.fetch_first_mapping(
            select(volunteer_documents.c.id, volunteer_documents.c.id_personal, volunteer_documents.c.filename)
            .where(volunteer_documents.c.id == document_id)
            .limit(1)
        )

    async def delete_document_record(self, document_id: int) -> None:
        await self.execute(delete(volunteer_documents).where(volunteer_documents.c.id == document_id))

    async def delete_volunteer(self, volunteer_id: int) -> None:
        async def remove(session) -> None:
            await session.execute(delete(role_assignments).where(role_assignments.c.id_personal == volunteer_id))
            await session.execute(delete(course_completions).where(course_completions.c.id_personal == volunteer_id))
            await session.execute(delete(volunteer_documents).where(volunteer_documents.c.id_personal == volunteer_id))
            await session.execute(delete(volunteer_cards).where(volunteer_cards.c.id_personal == volunteer_id))
            await session.execute(delete(volunteer_next_of_kin).where(volunteer_next_of_kin.c.id_personal == volunteer_id))
            await session.execute(delete(volunteer_photos).where(volunteer_photos.c.id_personal == volunteer_id))
            await session.execute(delete(volunteer_records).where(volunteer_records.c.id == volunteer_id))

        await self.execute_in_transaction(remove)


class _SearchColumns:
    def __init__(self) -> None:
        self.first_name = func.lower(func.coalesce(volunteer_records.c.fornavn, ""))
        self.last_name = func.lower(func.coalesce(volunteer_records.c.etternavn, ""))
        self.full_name = func.lower(
            func.concat_ws(" ", func.coalesce(volunteer_records.c.fornavn, ""), volunteer_records.c.etternavn)
        )
        self.email = func.lower(func.coalesce(volunteer_records.c.epost, ""))
        self.phone = func.lower(func.coalesce(volunteer_records.c.telefon, ""))


class _NameSortColumns:
    def __init__(self) -> None:
        self.last_name = func.coalesce(volunteer_records.c.etternavn, "")
        self.first_name = func.coalesce(volunteer_records.c.fornavn, "")


def _search_columns() -> _SearchColumns:
    return _SearchColumns()


def _name_sort_columns() -> _NameSortColumns:
    return _NameSortColumns()


def _volunteer_list_base_stmt(*, rank_score=None):
    points = _pingvin_points_subquery()
    last_semester = _last_semester_subquery()
    columns = [
        volunteer_records.c.id,
        volunteer_records.c.fornavn,
        volunteer_records.c.etternavn,
        volunteer_records.c.epost,
        volunteer_records.c.telefon,
        volunteer_photos.c.sha1,
        volunteer_photos.c.filetype,
        last_semester.c.last_semester,
        func.coalesce(points.c.pingvin_points, 0).label("pingvin_points"),
    ]
    if rank_score is not None:
        columns.append(rank_score)
    return select(*columns).select_from(
        volunteer_records.outerjoin(volunteer_photos, volunteer_photos.c.id_personal == volunteer_records.c.id)
        .outerjoin(points, points.c.id_personal == volunteer_records.c.id)
        .outerjoin(last_semester, last_semester.c.id_personal == volunteer_records.c.id)
    )


def _pingvin_points_subquery():
    return (
        select(
            role_assignments.c.id_personal.label("id_personal"),
            func.coalesce(func.sum(assignment_roles.c.pingvinpoeng), 0).label("pingvin_points"),
        )
        .select_from(role_assignments.outerjoin(assignment_roles, assignment_roles.c.id == role_assignments.c.id_verv))
        .group_by(role_assignments.c.id_personal)
        .subquery()
    )


def _last_semester_subquery():
    return (
        select(
            role_assignments.c.id_personal.label("id_personal"),
            func.max(role_assignments.c.semester).label("last_semester"),
        )
        .group_by(role_assignments.c.id_personal)
        .subquery()
    )
