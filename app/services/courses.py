from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Protocol

from app.postgrest import PostgrestClient, get_postgrest_client
from app.services.semester import format_semester_code


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
    person_id: int
    person_name: str
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


class CoursesServiceProtocol(Protocol):
    async def list_courses(self, query: str | None = None, limit: int = 100) -> list[CourseListItem]: ...
    async def get_course_detail(self, course_id: int) -> CourseDetail | None: ...


class CoursesService:
    def __init__(self, postgrest_client: PostgrestClient | None = None) -> None:
        self.postgrest_client = postgrest_client

    async def list_courses(self, query: str | None = None, limit: int = 100) -> list[CourseListItem]:
        if self.postgrest_client is None:
            raise RuntimeError("PostgREST-backed course reads are not configured yet.")
        filters: dict[str, str] = {}
        if query and query.strip():
            pattern = _postgrest_ilike_pattern(query.strip())
            filters["or"] = f"(navn.ilike.{pattern},beskrivelse.ilike.{pattern})"
        rows = await self.postgrest_client.select_rows(
            "kurs",
            select="id,navn,beskrivelse,opprettet",
            filters=filters,
            order="navn.asc,id.asc",
            limit=limit,
        )
        return [
            CourseListItem(
                course_id=row["id"],
                name=row["navn"],
                description=row["beskrivelse"],
                created_at=_coerce_datetime(row["opprettet"]),
            )
            for row in rows
        ]

    async def get_course_detail(self, course_id: int) -> CourseDetail | None:
        if self.postgrest_client is None:
            raise RuntimeError("PostgREST-backed course reads are not configured yet.")
        course_rows, group_rows, completion_rows = await asyncio.gather(
            self.postgrest_client.select_rows(
                "kurs",
                select="id,navn,beskrivelse,opprettet",
                filters={"id": f"eq.{course_id}"},
                limit=1,
            ),
            self.postgrest_client.select_rows(
                "grupper_kurs_kobling",
                select="grupper(id,navn)",
                filters={"id_kurs": f"eq.{course_id}"},
            ),
            self.postgrest_client.select_rows(
                "historie_kurs",
                select="id,gjennomfort_dato,personal(id,fornavn,etternavn)",
                filters={"id_kurs": f"eq.{course_id}"},
                order="gjennomfort_dato.desc,id.desc",
                limit=20,
            ),
        )
        if not course_rows:
            return None
        course_row = course_rows[0]
        return CourseDetail(
            course_id=course_row["id"],
            name=course_row["navn"],
            description=course_row["beskrivelse"],
            created_at=_coerce_datetime(course_row.get("opprettet")),
            required_groups=[
                RequiredGroupItem(
                    group_id=row["grupper"]["id"],
                    group_name=row["grupper"]["navn"],
                )
                for row in group_rows
                if row.get("grupper")
            ],
            recent_completions=[
                CourseCompletionItem(
                    completion_id=row["id"],
                    person_id=row["personal"]["id"],
                    person_name=_build_full_name(row["personal"].get("fornavn"), row["personal"].get("etternavn")),
                    completed_semester_code=row["gjennomfort_dato"],
                    completed_semester_label=format_semester_code(row["gjennomfort_dato"]) or str(row["gjennomfort_dato"]),
                )
                for row in completion_rows
            ],
        )


@lru_cache(maxsize=1)
def get_courses_service() -> CoursesService:
    try:
        postgrest_client = get_postgrest_client()
    except Exception:
        postgrest_client = None
    return CoursesService(postgrest_client=postgrest_client)


def _postgrest_ilike_pattern(value: str) -> str:
    escaped = value.replace(",", "\\,").replace("(", "\\(").replace(")", "\\)")
    return f"*{escaped}*"


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _build_full_name(first_name: str | None, last_name: str | None) -> str:
    return " ".join(part for part in [first_name, last_name] if part) or "Unknown person"
