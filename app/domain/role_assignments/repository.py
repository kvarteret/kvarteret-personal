"""Data access for position management.

Owns writes to ``role_assignments`` and ``course_completions``. The
volunteer/course existence checks read other modules' tables, which the
import contract allows (tables are the shared read seam).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, exists, insert, select, update

from app.db.repository import SqlAlchemyRepository
from app.domain.courses.tables import course_completions, courses
from app.domain.role_assignments.tables import assignment_roles, role_assignments
from app.domain.volunteers.tables import volunteer_records


class RoleAssignmentsRepository(SqlAlchemyRepository):
    async def volunteer_exists(self, volunteer_id: int) -> bool:
        return bool(
            await self.fetch_scalar(
                select(exists().where(volunteer_records.c.id == volunteer_id))
            )
        )

    async def course_exists(self, course_id: int) -> bool:
        return bool(
            await self.fetch_scalar(select(exists().where(courses.c.id == course_id)))
        )

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
        return bool(await self.fetch_scalar(select(exists().where(*filters))))

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
