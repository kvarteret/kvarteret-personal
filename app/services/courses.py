from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from time import perf_counter
from typing import Protocol

from sqlalchemy import BigInteger, Integer, Text, delete, func, insert, literal, or_, select, union_all, update

from app.db.repository import SqlAlchemyRepository
from app.db.tables import grupper, grupper_kurs_kobling, historie_kurs, kurs, personal
from app.observability import log_operation_timing
from app.services.common import build_full_name, coerce_datetime
from app.services.semester import format_semester_code

logger = logging.getLogger("app.performance")


class CourseDeleteBlockedError(ValueError):
    def __init__(self, blockers: list[str]) -> None:
        super().__init__("Course deletion is blocked.")
        self.blockers = blockers


@dataclass(slots=True)
class CourseListItem:
    course_id: int
    name: str
    description: str | None
    created_at: datetime | None


@dataclass(slots=True)
class RequiredGroupItem:
    group_id: int
    group_name: str


@dataclass(slots=True)
class CourseCompletionItem:
    completion_id: int
    volunteer_id: int
    volunteer_name: str
    completed_semester_code: int
    completed_semester_label: str


@dataclass(slots=True)
class CourseDetail:
    course_id: int
    name: str
    description: str | None
    created_at: datetime | None
    required_groups: list[RequiredGroupItem]
    recent_completions: list[CourseCompletionItem]
    delete_blockers: list[str]


class CoursesServiceProtocol(Protocol):
    async def list_courses(self, query: str | None = None, limit: int = 100) -> list[CourseListItem]: ...
    async def get_course_detail(self, course_id: int) -> CourseDetail | None: ...
    async def create_course(self, *, name: str, description: str | None) -> int: ...
    async def update_course(self, course_id: int, *, name: str, description: str | None) -> bool: ...
    async def delete_course(self, course_id: int) -> bool: ...


class CoursesService(SqlAlchemyRepository):
    async def list_courses(self, query: str | None = None, limit: int = 100) -> list[CourseListItem]:
        stmt = (
            select(kurs.c.id, kurs.c.navn, kurs.c.beskrivelse, kurs.c.opprettet)
            .order_by(kurs.c.navn.asc(), kurs.c.id.asc())
            .limit(limit)
        )
        if query and query.strip():
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(or_(kurs.c.navn.ilike(pattern), kurs.c.beskrivelse.ilike(pattern)))
        rows = await self.fetch_all_mappings(stmt)
        return [
            CourseListItem(
                course_id=row["id"],
                name=row["navn"],
                description=row["beskrivelse"],
                created_at=coerce_datetime(row["opprettet"]),
            )
            for row in rows
        ]

    async def get_course_detail(self, course_id: int) -> CourseDetail | None:
        started_at = perf_counter()
        course_select = select(
            literal("course").label("row_type"),
            kurs.c.id.label("course_id"),
            kurs.c.navn.label("course_name"),
            kurs.c.beskrivelse.label("course_description"),
            kurs.c.opprettet.label("course_created_at"),
            literal(None, type_=BigInteger()).label("group_id"),
            literal(None, type_=Text()).label("group_name"),
            literal(None, type_=BigInteger()).label("completion_id"),
            literal(None, type_=BigInteger()).label("volunteer_id"),
            literal(None, type_=Text()).label("volunteer_first_name"),
            literal(None, type_=Text()).label("volunteer_last_name"),
            literal(None, type_=Integer()).label("completed_semester"),
        ).where(kurs.c.id == course_id)
        groups_select = (
            select(
                literal("group").label("row_type"),
                literal(None, type_=BigInteger()).label("course_id"),
                literal(None, type_=Text()).label("course_name"),
                literal(None, type_=Text()).label("course_description"),
                literal(None, type_=kurs.c.opprettet.type).label("course_created_at"),
                grupper.c.id.label("group_id"),
                grupper.c.navn.label("group_name"),
                literal(None, type_=BigInteger()).label("completion_id"),
                literal(None, type_=BigInteger()).label("volunteer_id"),
                literal(None, type_=Text()).label("volunteer_first_name"),
                literal(None, type_=Text()).label("volunteer_last_name"),
                literal(None, type_=Integer()).label("completed_semester"),
            )
            .select_from(grupper_kurs_kobling.join(grupper, grupper.c.id == grupper_kurs_kobling.c.id_gruppe))
            .where(grupper_kurs_kobling.c.id_kurs == course_id)
        )
        recent_completions = (
            select(
                historie_kurs.c.id,
                historie_kurs.c.gjennomfort_dato,
                personal.c.id.label("volunteer_id"),
                personal.c.fornavn,
                personal.c.etternavn,
            )
            .select_from(historie_kurs.join(personal, personal.c.id == historie_kurs.c.id_personal))
            .where(historie_kurs.c.id_kurs == course_id)
            .order_by(historie_kurs.c.gjennomfort_dato.desc(), historie_kurs.c.id.desc())
            .limit(20)
            .subquery()
        )
        completions_select = select(
            literal("completion").label("row_type"),
            literal(None, type_=BigInteger()).label("course_id"),
            literal(None, type_=Text()).label("course_name"),
            literal(None, type_=Text()).label("course_description"),
            literal(None, type_=kurs.c.opprettet.type).label("course_created_at"),
            literal(None, type_=BigInteger()).label("group_id"),
            literal(None, type_=Text()).label("group_name"),
            recent_completions.c.id.label("completion_id"),
            recent_completions.c.volunteer_id.label("volunteer_id"),
            recent_completions.c.fornavn.label("volunteer_first_name"),
            recent_completions.c.etternavn.label("volunteer_last_name"),
            recent_completions.c.gjennomfort_dato.label("completed_semester"),
        )
        rows = await self.fetch_all_mappings(union_all(course_select, groups_select, completions_select))
        log_operation_timing(logger, operation="courses.detail", started_at=started_at, details={"course_id": course_id})
        course_row = next((row for row in rows if row["row_type"] == "course"), None)
        if course_row is None:
            return None
        delete_blockers = await self._get_course_delete_blockers(course_id)
        required_groups: list[RequiredGroupItem] = []
        seen_group_ids: set[int] = set()
        recent_completion_items: list[CourseCompletionItem] = []
        seen_completion_ids: set[int] = set()
        for row in rows:
            if row["row_type"] == "group" and row["group_id"] is not None and row["group_id"] not in seen_group_ids:
                seen_group_ids.add(row["group_id"])
                required_groups.append(RequiredGroupItem(group_id=row["group_id"], group_name=row["group_name"]))
            if (
                row["row_type"] == "completion"
                and row["completion_id"] is not None
                and row["completion_id"] not in seen_completion_ids
            ):
                seen_completion_ids.add(row["completion_id"])
                recent_completion_items.append(
                    CourseCompletionItem(
                        completion_id=row["completion_id"],
                        volunteer_id=row["volunteer_id"],
                        volunteer_name=build_full_name(row.get("volunteer_first_name"), row.get("volunteer_last_name")),
                        completed_semester_code=row["completed_semester"],
                        completed_semester_label=format_semester_code(row["completed_semester"])
                        or str(row["completed_semester"]),
                    )
                )
        return CourseDetail(
            course_id=course_row["course_id"],
            name=course_row["course_name"],
            description=course_row["course_description"],
            created_at=coerce_datetime(course_row.get("course_created_at")),
            required_groups=sorted(required_groups, key=lambda item: (item.group_name.lower(), item.group_id)),
            recent_completions=sorted(
                recent_completion_items,
                key=lambda item: (item.completed_semester_code, item.completion_id),
                reverse=True,
            ),
            delete_blockers=delete_blockers,
        )

    async def create_course(self, *, name: str, description: str | None) -> int:
        row = await self.execute_one_mapping(
            insert(kurs)
            .values(
                navn=name.strip(),
                beskrivelse=(description.strip() if description and description.strip() else None),
                opprettet=datetime.now(UTC),
            )
            .returning(kurs.c.id)
        )
        return row["id"]

    async def update_course(self, course_id: int, *, name: str, description: str | None) -> bool:
        async def callback(session):
            result = await session.execute(
                update(kurs)
                .where(kurs.c.id == course_id)
                .values(
                    navn=name.strip(),
                    beskrivelse=(description.strip() if description and description.strip() else None),
                )
                .returning(kurs.c.id)
            )
            row = result.first()
            return row[0] if row is not None else None

        updated_course_id = await self.execute_in_transaction(callback)
        return updated_course_id == course_id

    async def delete_course(self, course_id: int) -> bool:
        blockers = await self._get_course_delete_blockers(course_id)
        if blockers:
            raise CourseDeleteBlockedError(blockers)

        async def callback(session):
            await session.execute(delete(grupper_kurs_kobling).where(grupper_kurs_kobling.c.id_kurs == course_id))
            result = await session.execute(delete(kurs).where(kurs.c.id == course_id).returning(kurs.c.id))
            row = result.first()
            return row[0] if row is not None else None

        deleted_course_id = await self.execute_in_transaction(callback)
        return deleted_course_id == course_id

    async def _get_course_delete_blockers(self, course_id: int) -> list[str]:
        completion_count = await self.fetch_scalar(
            select(func.count()).select_from(historie_kurs).where(historie_kurs.c.id_kurs == course_id)
        )
        blockers: list[str] = []
        if completion_count:
            blockers.append("Kurset har fullføringer og kan ikke slettes.")
        return blockers
