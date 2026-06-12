"""Write side of the volunteers module.

Reads live in ``app.domain.volunteers.queries``; this repository holds
the statements that change volunteer state (profile, relations, photo
records, position management, offboarding deletion).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, exists, insert, select, update

from app.db.repository import SqlAlchemyRepository
from app.domain.courses.tables import course_completions, courses
from app.domain.role_assignments.tables import assignment_roles, role_assignments
from app.domain.volunteer_applications.tables import volunteer_application_invites
from app.domain.volunteers.tables import (
    volunteer_cards,
    volunteer_next_of_kin,
    volunteer_photos,
    volunteer_records,
)


class VolunteersRepository(SqlAlchemyRepository):
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
        if existing:
            await self.execute(
                update(volunteer_photos)
                .where(volunteer_photos.c.volunteer_id == volunteer_id)
                .values(filetype=extension)
            )
        else:
            await self.execute(
                insert(volunteer_photos).values(
                    volunteer_id=volunteer_id, sha1=filename_hash, filetype=extension
                )
            )

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
        await self.execute(
            delete(volunteer_cards).where(
                volunteer_cards.c.volunteer_id == volunteer_id
            )
        )
        await self.execute(
            delete(volunteer_next_of_kin).where(
                volunteer_next_of_kin.c.volunteer_id == volunteer_id
            )
        )
        if card_numbers:
            await self.session.execute(
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
            await self.session.execute(
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
        # Detach the application record instead of deleting it: the
        # invite row is lifecycle history. Status stays 'promoted',
        # so the application does not resurface as pending.
        await self.execute(
            update(volunteer_application_invites)
            .where(
                volunteer_application_invites.c.promoted_volunteer_id
                == volunteer_id
            )
            .values(promoted_volunteer_id=None)
        )
        await self.execute(
            delete(role_assignments).where(
                role_assignments.c.volunteer_id == volunteer_id
            )
        )
        await self.execute(
            delete(course_completions).where(
                course_completions.c.volunteer_id == volunteer_id
            )
        )
        await self.execute(
            delete(volunteer_cards).where(
                volunteer_cards.c.volunteer_id == volunteer_id
            )
        )
        await self.execute(
            delete(volunteer_next_of_kin).where(
                volunteer_next_of_kin.c.volunteer_id == volunteer_id
            )
        )
        await self.execute(
            delete(volunteer_photos).where(
                volunteer_photos.c.volunteer_id == volunteer_id
            )
        )
        await self.execute(
            delete(volunteer_records).where(volunteer_records.c.id == volunteer_id)
        )
