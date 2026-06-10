from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Float,
    Text,
    and_,
    case,
    delete,
    exists,
    func,
    insert,
    literal,
    or_,
    select,
    union_all,
    update,
)

from app.db.repository import SqlAlchemyRepository
from app.db.tables import (
    assignment_roles,
    course_completions,
    courses,
    groups,
    role_assignments,
    volunteer_application_invites,
    volunteer_application_group_members,
    volunteer_cards,
    volunteer_next_of_kin,
    volunteer_photos,
    volunteer_records,
)
from app.infrastructure.formatting.semester import get_current_semester_code


class VolunteersRepository(SqlAlchemyRepository):
    async def list_volunteers_page(
        self,
        *,
        limit: int,
        after_last_name: str | None = None,
        after_first_name: str | None = None,
        after_volunteer_id: int | None = None,
        only_active: bool = False,
    ) -> list[dict[str, Any]]:
        name_sort = _name_sort_columns()
        active_volunteers = (
            _current_active_volunteers_subquery() if only_active else None
        )
        stmt = (
            _volunteer_list_base_stmt(active_volunteers=active_volunteers)
            .order_by(
                name_sort.last_name.asc(),
                name_sort.first_name.asc(),
                volunteer_records.c.id.asc(),
            )
            .limit(limit)
        )
        if (
            after_volunteer_id is not None
            and after_last_name is not None
            and after_first_name is not None
        ):
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

    async def search_volunteers_page(
        self,
        *,
        normalized_query: str,
        limit: int,
        offset: int = 0,
        only_active: bool = False,
    ) -> list[dict[str, Any]]:
        return await self.fetch_all_mappings(
            _build_volunteer_search_stmt(
                normalized_query=normalized_query,
                limit=limit,
                offset=offset,
                only_active=only_active,
            )
        )

    async def count_volunteers(self, *, only_active: bool = False) -> int:
        active_volunteers = (
            _current_active_volunteers_subquery() if only_active else None
        )
        base = select(volunteer_records.c.id)
        if active_volunteers is not None:
            base = base.select_from(
                volunteer_records.join(
                    active_volunteers,
                    active_volunteers.c.volunteer_id == volunteer_records.c.id,
                )
            )
        stmt = select(func.count()).select_from(base.subquery())
        return await self.fetch_scalar(stmt) or 0

    async def count_volunteers_search(
        self, *, normalized_query: str, only_active: bool = False
    ) -> int:
        stmt = _build_volunteer_search_count_stmt(
            normalized_query=normalized_query, only_active=only_active
        )
        return await self.fetch_scalar(stmt) or 0

    async def fetch_volunteer_shell_row(
        self, volunteer_id: int
    ) -> dict[str, Any] | None:
        points = _pingvin_points_subquery()
        discount_levels = _current_discount_level_subquery()
        first_choice_group = groups.alias("first_choice_group")
        second_choice_group = groups.alias("second_choice_group")
        stmt = (
            select(
                volunteer_records.c.id,
                volunteer_records.c.first_name,
                volunteer_records.c.last_name,
                volunteer_records.c.email,
                volunteer_records.c.phone,
                volunteer_records.c.birth_date,
                volunteer_records.c.created_at,
                volunteer_records.c.gender,
                volunteer_records.c.street_address,
                volunteer_records.c.postal_code,
                func.coalesce(points.c.pingvin_points, 0).label("pingvin_points"),
                discount_levels.c.current_discount_level,
                volunteer_photos.c.sha1,
                volunteer_photos.c.filetype,
                volunteer_application_invites.c.id.label("registration_id"),
                volunteer_application_invites.c.created_at.label("registration_created_at"),
                volunteer_application_invites.c.source.label("registration_source"),
                volunteer_application_invites.c.status.label("registration_status"),
                first_choice_group.c.name.label("first_choice_group_name"),
                second_choice_group.c.name.label("second_choice_group_name"),
                volunteer_application_group_members.c.group_id.label("registration_group_id"),
                volunteer_application_group_members.c.role.label("registration_group_role"),
                volunteer_application_group_members.c.status.label("registration_group_status"),
            )
            .select_from(
                volunteer_records.outerjoin(
                    volunteer_photos,
                    volunteer_photos.c.volunteer_id == volunteer_records.c.id,
                )
                .outerjoin(
                    points,
                    points.c.volunteer_id == volunteer_records.c.id,
                )
                .outerjoin(
                    discount_levels,
                    discount_levels.c.volunteer_id == volunteer_records.c.id,
                )
                .outerjoin(
                    volunteer_application_invites,
                    volunteer_application_invites.c.promoted_volunteer_id == volunteer_records.c.id,
                )
                .outerjoin(
                    first_choice_group,
                    first_choice_group.c.id == volunteer_application_invites.c.first_choice_group_id,
                )
                .outerjoin(
                    second_choice_group,
                    second_choice_group.c.id == volunteer_application_invites.c.second_choice_group_id,
                )
                .outerjoin(
                    volunteer_application_group_members,
                    volunteer_application_group_members.c.invite_id == volunteer_application_invites.c.id,
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
                role_assignments.c.group_id,
                role_assignments.c.role_id,
                role_assignments.c.semester,
                role_assignments.c.contract_signed,
                groups.c.name.label("group_name"),
                assignment_roles.c.name.label("role_name"),
                assignment_roles.c.penguin_points,
            )
            .select_from(
                role_assignments.join(
                    groups, groups.c.id == role_assignments.c.group_id
                ).outerjoin(
                    assignment_roles,
                    assignment_roles.c.id == role_assignments.c.role_id,
                )
            )
            .where(role_assignments.c.volunteer_id == volunteer_id)
            .order_by(role_assignments.c.semester.desc(), role_assignments.c.id.desc())
            .limit(limit)
        )
        return await self.fetch_all_mappings(stmt)

    async def fetch_volunteer_course_completion_rows(
        self,
        volunteer_id: int,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(
                course_completions.c.id,
                course_completions.c.course_id,
                course_completions.c.completed_semester,
                courses.c.name.label("course_name"),
            )
            .select_from(
                course_completions.join(
                    courses, courses.c.id == course_completions.c.course_id
                )
            )
            .where(course_completions.c.volunteer_id == volunteer_id)
            .order_by(
                course_completions.c.completed_semester.desc(),
                course_completions.c.id.desc(),
            )
            .limit(limit)
        )
        return await self.fetch_all_mappings(stmt)

    async def list_assignment_group_rows(self) -> list[dict[str, Any]]:
        stmt = select(groups.c.id, groups.c.name, groups.c.is_active).order_by(
            groups.c.is_active.desc(), groups.c.name.asc(), groups.c.id.asc()
        )
        return await self.fetch_all_mappings(stmt)

    async def list_assignment_role_rows(self, group_id: int) -> list[dict[str, Any]]:
        stmt = (
            select(
                assignment_roles.c.id,
                assignment_roles.c.group_id,
                assignment_roles.c.name,
                assignment_roles.c.penguin_points,
            )
            .where(assignment_roles.c.group_id == group_id)
            .order_by(
                assignment_roles.c.name.asc().nullslast(), assignment_roles.c.id.asc()
            )
        )
        return await self.fetch_all_mappings(stmt)

    async def fetch_volunteer_relation_rows(
        self, volunteer_id: int
    ) -> list[dict[str, Any]]:
        kin_stmt = select(
            literal("kin").label("relation_type"),
            volunteer_next_of_kin.c.id.label("relation_id"),
            volunteer_next_of_kin.c.name.label("primary_text"),
            volunteer_next_of_kin.c.phone.label("secondary_text"),
            volunteer_next_of_kin.c.created_at.label("created_at"),
        ).where(volunteer_next_of_kin.c.volunteer_id == volunteer_id)
        card_stmt = select(
            literal("card").label("relation_type"),
            volunteer_cards.c.id.label("relation_id"),
            volunteer_cards.c.card_number.label("primary_text"),
            literal(None, type_=Text()).label("secondary_text"),
            volunteer_cards.c.created_at.label("created_at"),
        ).where(volunteer_cards.c.volunteer_id == volunteer_id)
        relations = union_all(kin_stmt, card_stmt).subquery()
        stmt = select(
            relations.c.relation_type,
            relations.c.relation_id,
            relations.c.primary_text,
            relations.c.secondary_text,
            relations.c.created_at,
        ).order_by(relations.c.created_at.desc(), relations.c.relation_id.desc())
        return await self.fetch_all_mappings(stmt)

    async def volunteer_exists(self, volunteer_id: int) -> bool:
        return bool(
            await self.fetch_scalar(
                select(exists().where(volunteer_records.c.id == volunteer_id))
            )
        )

    async def find_volunteer_id_by_email(self, email: str) -> int | None:
        return await self.fetch_scalar(
            select(volunteer_records.c.id)
            .where(
                func.lower(func.coalesce(volunteer_records.c.email, ""))
                == email.lower()
            )
            .limit(1)
        )

    async def course_exists(self, course_id: int) -> bool:
        return bool(
            await self.fetch_scalar(select(exists().where(courses.c.id == course_id)))
        )

    async def fetch_photo_record(self, volunteer_id: int):
        return await self.fetch_first_mapping(
            select(volunteer_photos.c.sha1, volunteer_photos.c.filetype)
            .where(volunteer_photos.c.volunteer_id == volunteer_id)
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
                    .where(volunteer_photos.c.volunteer_id == volunteer_id)
                    .values(filetype=extension)
                )
            else:
                await session.execute(
                    insert(volunteer_photos).values(
                        volunteer_id=volunteer_id, sha1=filename_hash, filetype=extension
                    )
                )

        await save(self.session)

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
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                birth_date=birth_date,
                gender=gender_code,
                street_address=address,
                postal_code=postal_code,
            )
        )

    async def replace_volunteer_relations(
        self,
        *,
        volunteer_id: int,
        card_numbers: list[str],
        next_of_kin: list[dict[str, str]],
    ) -> None:
        created_at = datetime.now(UTC)

        async def replace(session) -> None:
            await session.execute(
                delete(volunteer_cards).where(
                    volunteer_cards.c.volunteer_id == volunteer_id
                )
            )
            await session.execute(
                delete(volunteer_next_of_kin).where(
                    volunteer_next_of_kin.c.volunteer_id == volunteer_id
                )
            )
            if card_numbers:
                await session.execute(
                    insert(volunteer_cards),
                    [
                        {
                            "volunteer_id": volunteer_id,
                            "card_number": card_number,
                            "created_at": created_at,
                        }
                        for card_number in card_numbers
                    ],
                )
            if next_of_kin:
                await session.execute(
                    insert(volunteer_next_of_kin),
                    [
                        {
                            "volunteer_id": volunteer_id,
                            "name": item["name"],
                            "phone": item["phone"],
                            "created_at": created_at,
                        }
                        for item in next_of_kin
                    ],
                )

        await replace(self.session)

    async def course_completion_exists(
        self,
        *,
        volunteer_id: int,
        course_id: int,
        semester_code: int,
        exclude_completion_id: int | None = None,
    ) -> bool:
        filters = [
            course_completions.c.volunteer_id == volunteer_id,
            course_completions.c.course_id == course_id,
            course_completions.c.completed_semester == semester_code,
        ]
        if exclude_completion_id is not None:
            filters.append(course_completions.c.id != exclude_completion_id)
        return bool(await self.fetch_scalar(select(exists().where(*filters))))

    async def create_course_completion(
        self,
        *,
        volunteer_id: int,
        course_id: int,
        semester_code: int,
    ) -> dict[str, Any]:
        stmt = (
            insert(course_completions)
            .values(
                volunteer_id=volunteer_id,
                course_id=course_id,
                completed_semester=semester_code,
            )
            .returning(
                course_completions.c.id,
                course_completions.c.volunteer_id,
                course_completions.c.course_id,
                course_completions.c.completed_semester,
            )
        )
        return await self.execute_one_mapping(stmt)

    async def fetch_course_completion_record(
        self, completion_id: int
    ) -> dict[str, Any] | None:
        stmt = (
            select(
                course_completions.c.id,
                course_completions.c.volunteer_id,
                course_completions.c.course_id,
                course_completions.c.completed_semester,
            )
            .where(course_completions.c.id == completion_id)
            .limit(1)
        )
        return await self.fetch_first_mapping(stmt)

    async def delete_course_completion(self, completion_id: int) -> None:
        await self.execute(
            delete(course_completions).where(course_completions.c.id == completion_id)
        )

    async def role_belongs_to_group(self, *, group_id: int, role_id: int) -> bool:
        return bool(
            await self.fetch_scalar(
                select(
                    exists().where(
                        assignment_roles.c.id == role_id,
                        assignment_roles.c.group_id == group_id,
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
            role_assignments.c.volunteer_id == volunteer_id,
            role_assignments.c.group_id == group_id,
            role_assignments.c.role_id == role_id,
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
                volunteer_id=volunteer_id,
                group_id=group_id,
                role_id=role_id,
                semester=semester_code,
                contract_signed=contract_signed,
            )
        )

    async def fetch_role_assignment_record(self, history_id: int):
        return await self.fetch_first_mapping(
            select(
                role_assignments.c.id,
                role_assignments.c.volunteer_id,
                role_assignments.c.group_id,
                role_assignments.c.role_id,
                role_assignments.c.semester,
                role_assignments.c.contract_signed,
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
                group_id=group_id,
                role_id=role_id,
                semester=semester_code,
                contract_signed=contract_signed,
            )
        )

    async def delete_role_assignment(self, history_id: int) -> None:
        await self.execute(
            delete(role_assignments).where(role_assignments.c.id == history_id)
        )

    async def delete_photo_record(self, volunteer_id: int) -> None:
        await self.execute(
            delete(volunteer_photos).where(
                volunteer_photos.c.volunteer_id == volunteer_id
            )
        )

    async def delete_volunteer(self, volunteer_id: int) -> None:
        async def remove(session) -> None:
            await session.execute(
                delete(role_assignments).where(
                    role_assignments.c.volunteer_id == volunteer_id
                )
            )
            await session.execute(
                delete(course_completions).where(
                    course_completions.c.volunteer_id == volunteer_id
                )
            )
            await session.execute(
                delete(volunteer_cards).where(
                    volunteer_cards.c.volunteer_id == volunteer_id
                )
            )
            await session.execute(
                delete(volunteer_next_of_kin).where(
                    volunteer_next_of_kin.c.volunteer_id == volunteer_id
                )
            )
            await session.execute(
                delete(volunteer_photos).where(
                    volunteer_photos.c.volunteer_id == volunteer_id
                )
            )
            await session.execute(
                delete(volunteer_records).where(volunteer_records.c.id == volunteer_id)
            )

        await remove(self.session)


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


def _search_columns(assignment_search_text=None) -> _SearchColumns:
    return _SearchColumns(assignment_search_text)


def _name_sort_columns() -> _NameSortColumns:
    return _NameSortColumns()


def _volunteer_list_base_stmt(*, rank_score=None, active_volunteers=None):
    points = _pingvin_points_subquery()
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


def _pingvin_points_subquery():
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


def _current_discount_level_subquery():
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


def _current_active_volunteers_subquery():
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


def _build_volunteer_search_stmt(
    *, normalized_query: str, limit: int, offset: int, only_active: bool = False
):
    assignment_search_text = _assignment_search_text_subquery(
        only_current_semester=only_active
    )
    active_volunteers = _current_active_volunteers_subquery() if only_active else None
    search = _search_columns(assignment_search_text)
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
        _volunteer_list_base_stmt(
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


def _build_volunteer_search_count_stmt(
    *, normalized_query: str, only_active: bool = False
):
    assignment_search_text = _assignment_search_text_subquery(
        only_current_semester=only_active
    )
    active_volunteers = _current_active_volunteers_subquery() if only_active else None
    search = _search_columns(assignment_search_text)
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
