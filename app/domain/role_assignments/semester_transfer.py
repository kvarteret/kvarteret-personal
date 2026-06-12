from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, insert, select

from app.db.repository import SqlAlchemyRepository
from app.domain.groups.tables import groups
from app.domain.role_assignments.tables import assignment_roles, role_assignments
from app.domain.volunteers.tables import volunteer_records
from app.infrastructure.formatting.semester import (
    format_semester_code,
    get_current_semester_code,
    get_next_semester_code,
)


class SemesterTransferError(RuntimeError):
    pass


class SemesterTransferGroupNotFoundError(SemesterTransferError):
    pass


@dataclass(slots=True)
class SemesterTransferCandidate:
    volunteer_id: int
    volunteer_name: str
    role_id: int | None
    role_name: str | None
    contract_signed: bool
    source_history_id: int


@dataclass(slots=True)
class SemesterTransferPreview:
    group_id: int
    group_name: str
    source_semester: int
    source_semester_label: str | None
    target_semester: int
    target_semester_label: str | None
    candidates: list[SemesterTransferCandidate]


@dataclass(slots=True)
class SemesterTransferEntry:
    volunteer_id: int
    role_id: int | None
    contract_signed: bool = False


class SemesterTransferService(SqlAlchemyRepository):
    async def preview_transfer(
        self,
        group_id: int,
        source_semester: int | None = None,
        target_semester: int | None = None,
    ) -> SemesterTransferPreview:
        group_stmt = (
            select(groups.c.id, groups.c.name)
            .where(groups.c.id == group_id)
            .limit(1)
        )
        source_semester_stmt = select(func.max(role_assignments.c.semester)).where(
            role_assignments.c.group_id == group_id
        )
        session = self.session
        group_row = (await session.execute(group_stmt)).mappings().first()
        if group_row is None:
            raise SemesterTransferGroupNotFoundError(
                f"Group {group_id} was not found."
            )
        resolved_source = (
            source_semester
            or (await session.execute(source_semester_stmt)).scalar_one_or_none()
        )
        if resolved_source is None:
            resolved_source = get_current_semester_code()

        members_stmt = (
            select(
                role_assignments.c.id,
                role_assignments.c.volunteer_id,
                func.concat_ws(" ", volunteer_records.c.first_name, volunteer_records.c.last_name).label(
                    "volunteer_name"
                ),
                role_assignments.c.role_id,
                assignment_roles.c.name.label("verv_navn"),
                role_assignments.c.contract_signed,
            )
            .select_from(
                role_assignments.join(
                    volunteer_records, volunteer_records.c.id == role_assignments.c.volunteer_id
                ).outerjoin(assignment_roles, assignment_roles.c.id == role_assignments.c.role_id)
            )
            .where(role_assignments.c.group_id == group_id)
            .where(role_assignments.c.semester == resolved_source)
            .order_by(
                volunteer_records.c.last_name.asc(),
                volunteer_records.c.first_name.asc(),
                role_assignments.c.id.asc(),
            )
        )
        member_rows = (await session.execute(members_stmt)).mappings().all()

        resolved_target = target_semester or _default_target_semester(resolved_source)
        return SemesterTransferPreview(
            group_id=group_row["id"],
            group_name=group_row["name"],
            source_semester=resolved_source,
            source_semester_label=format_semester_code(resolved_source),
            target_semester=resolved_target,
            target_semester_label=format_semester_code(resolved_target),
            candidates=[
                SemesterTransferCandidate(
                    volunteer_id=row["volunteer_id"],
                    volunteer_name=row["volunteer_name"]
                    or f"Volunteer {row['volunteer_id']}",
                    role_id=row["role_id"],
                    role_name=row["verv_navn"],
                    contract_signed=row["contract_signed"],
                    source_history_id=row["id"],
                )
                for row in member_rows
            ],
        )

    async def apply_transfer(
        self, group_id: int, target_semester: int, entries: list[SemesterTransferEntry]
    ) -> int:
        session = self.session
        group_exists = await session.scalar(
            select(groups.c.id).where(groups.c.id == group_id).limit(1)
        )
        if group_exists is None:
            raise SemesterTransferGroupNotFoundError(f"Group {group_id} was not found.")
        if not entries:
            return 0
        volunteer_ids = [entry.volunteer_id for entry in entries]
        if not volunteer_ids:
            return 0
        existing_stmt = (
            select(role_assignments.c.volunteer_id)
            .where(role_assignments.c.group_id == group_id)
            .where(role_assignments.c.semester == target_semester)
            .where(role_assignments.c.volunteer_id.in_(volunteer_ids))
        )
        session = self.session
        existing_volunteers = {
            row["volunteer_id"]
            for row in (await session.execute(existing_stmt)).mappings().all()
        }
        values = [
            {
                "volunteer_id": entry.volunteer_id,
                "group_id": group_id,
                "role_id": entry.role_id,
                "semester": target_semester,
                "contract_signed": entry.contract_signed,
            }
            for entry in entries
            if entry.volunteer_id not in existing_volunteers
        ]
        if not values:
            return 0
        session = self.session
        await session.execute(insert(role_assignments), values)
        return len(values)


def _default_target_semester(source_semester: int) -> int:
    current = get_current_semester_code()
    return (
        current
        if current > source_semester
        else get_next_semester_code(source_semester)
    )
