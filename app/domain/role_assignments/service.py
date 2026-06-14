"""Position management: assigning volunteers to roles and courses.

Owned by the role_assignments module together with the semester
transfer. Writes here change what the volunteer detail page shows, so
the service notifies the volunteers read side through the injected
``invalidate_volunteer_cache`` callable — wiring happens in
``app/runtime.py``; there is no cross-module import.
"""

from __future__ import annotations

from collections.abc import Callable

from app.domain.role_assignments.models import (
    CourseCompletionNotFoundError,
    DuplicateCourseCompletionError,
    DuplicateRoleAssignmentError,
    InvalidCourseCompletionError,
    InvalidRoleAssignmentError,
    RoleAssignmentNotFoundError,
    RoleAssignmentsError,
    VolunteerNotFoundError,
)
from app.domain.role_assignments.repository import RoleAssignmentsRepository
from app.infrastructure.formatting.semester import format_semester_code


class RoleAssignmentsService:
    def __init__(
        self,
        repository: RoleAssignmentsRepository,
        invalidate_volunteer_cache: Callable[[int], None],
    ) -> None:
        self.repository = repository
        self._invalidate_volunteer_cache = invalidate_volunteer_cache

    async def add_course_completion(
        self,
        *,
        volunteer_id: int,
        course_id: int,
        year: int,
        term: int,
    ) -> None:
        semester_code = _build_semester_code(
            year=year, term=term, error_cls=InvalidCourseCompletionError
        )
        if not await self.repository.volunteer_exists(volunteer_id):
            raise VolunteerNotFoundError(f"Volunteer {volunteer_id} was not found.")
        if not await self.repository.course_exists(course_id):
            raise InvalidCourseCompletionError("Selected course was not found.")
        if await self.repository.course_completion_exists(
            volunteer_id=volunteer_id,
            course_id=course_id,
            semester_code=semester_code,
        ):
            raise DuplicateCourseCompletionError(
                "Dette kurset er allerede registrert for valgt semester."
            )
        await self.repository.create_course_completion(
            volunteer_id=volunteer_id,
            course_id=course_id,
            semester_code=semester_code,
        )
        self._invalidate_volunteer_cache(volunteer_id)

    async def delete_course_completion_for_volunteer(
        self, volunteer_id: int, completion_id: int
    ) -> None:
        row = await self.repository.fetch_course_completion_record(completion_id)
        if not row or row["volunteer_id"] != volunteer_id:
            raise CourseCompletionNotFoundError(
                f"Course completion {completion_id} was not found."
            )
        await self.repository.delete_course_completion(completion_id)
        self._invalidate_volunteer_cache(volunteer_id)

    async def add_role_assignment(
        self,
        *,
        volunteer_id: int,
        group_id: int,
        role_id: int,
        year: int,
        term: int,
        contract_signed: bool,
    ) -> None:
        semester_code = _build_semester_code(
            year=year, term=term, error_cls=InvalidRoleAssignmentError
        )
        if not await self.repository.volunteer_exists(volunteer_id):
            raise VolunteerNotFoundError(f"Volunteer {volunteer_id} was not found.")
        if not await self.repository.role_belongs_to_group(
            group_id=group_id, role_id=role_id
        ):
            raise InvalidRoleAssignmentError(
                "Selected name does not belong to the selected group."
            )
        if await self.repository.role_assignment_exists(
            volunteer_id=volunteer_id,
            group_id=group_id,
            role_id=role_id,
            semester_code=semester_code,
        ):
            raise DuplicateRoleAssignmentError(
                "This name is already registered for the selected semester."
            )
        await self.repository.create_role_assignment(
            volunteer_id=volunteer_id,
            group_id=group_id,
            role_id=role_id,
            semester_code=semester_code,
            contract_signed=contract_signed,
        )
        self._invalidate_volunteer_cache(volunteer_id)

    async def update_role_assignment_for_volunteer(
        self,
        volunteer_id: int,
        history_id: int,
        *,
        group_id: int,
        role_id: int,
        year: int,
        term: int,
        contract_signed: bool,
    ) -> None:
        row = await self.repository.fetch_role_assignment_record(history_id)
        if not row or row["volunteer_id"] != volunteer_id:
            raise RoleAssignmentNotFoundError(
                f"Role assignment {history_id} was not found."
            )
        semester_code = _build_semester_code(
            year=year, term=term, error_cls=InvalidRoleAssignmentError
        )
        if not await self.repository.role_belongs_to_group(
            group_id=group_id, role_id=role_id
        ):
            raise InvalidRoleAssignmentError(
                "Selected name does not belong to the selected group."
            )
        if await self.repository.role_assignment_exists(
            volunteer_id=volunteer_id,
            group_id=group_id,
            role_id=role_id,
            semester_code=semester_code,
            exclude_history_id=history_id,
        ):
            raise DuplicateRoleAssignmentError(
                "This name is already registered for the selected semester."
            )
        await self.repository.update_role_assignment(
            history_id,
            group_id=group_id,
            role_id=role_id,
            semester_code=semester_code,
            contract_signed=contract_signed,
        )
        self._invalidate_volunteer_cache(volunteer_id)

    async def delete_role_assignment_for_volunteer(
        self, volunteer_id: int, history_id: int
    ) -> None:
        row = await self.repository.fetch_role_assignment_record(history_id)
        if not row or row["volunteer_id"] != volunteer_id:
            raise RoleAssignmentNotFoundError(
                f"Role assignment {history_id} was not found."
            )
        await self.repository.delete_role_assignment(history_id)
        self._invalidate_volunteer_cache(volunteer_id)


def _build_semester_code(
    *, year: int, term: int, error_cls: type[RoleAssignmentsError]
) -> int:
    if year < 1900 or year > 3000:
        raise error_cls("Year must be between 1900 and 3000.")
    if term not in {1, 2}:
        raise error_cls("Semester must be Vår or Høst.")
    semester_code = year * 10 + term
    if not format_semester_code(semester_code):
        raise error_cls("Unsupported semester code.")
    return semester_code
