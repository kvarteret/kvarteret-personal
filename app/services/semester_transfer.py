from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, insert, select

from app.db.session import get_session_factory
from app.db.tables import grupper, historie, personal, verv
from app.services.semester import format_semester_code, get_current_semester_code, get_next_semester_code


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


class SemesterTransferService:
    async def preview_transfer(
        self,
        group_id: int,
        source_semester: int | None = None,
        target_semester: int | None = None,
    ) -> SemesterTransferPreview:
        group_stmt = select(grupper.c.id, grupper.c.navn).where(grupper.c.id == group_id).limit(1)
        source_semester_stmt = select(func.max(historie.c.semester)).where(historie.c.id_gruppe == group_id)
        async with get_session_factory()() as session:
            group_row = (await session.execute(group_stmt)).mappings().first()
            if group_row is None:
                raise SemesterTransferGroupNotFoundError(f"Group {group_id} was not found.")
            resolved_source = source_semester or (await session.execute(source_semester_stmt)).scalar_one_or_none()
            if resolved_source is None:
                resolved_source = get_current_semester_code()

            members_stmt = (
                select(
                    historie.c.id,
                    historie.c.id_personal,
                    func.concat_ws(" ", personal.c.fornavn, personal.c.etternavn).label("volunteer_name"),
                    historie.c.id_verv,
                    verv.c.verv.label("verv_navn"),
                    historie.c.signert_kontrakt,
                )
                .select_from(
                    historie.join(personal, personal.c.id == historie.c.id_personal).outerjoin(verv, verv.c.id == historie.c.id_verv)
                )
                .where(historie.c.id_gruppe == group_id)
                .where(historie.c.semester == resolved_source)
                .order_by(personal.c.etternavn.asc(), personal.c.fornavn.asc(), historie.c.id.asc())
            )
            member_rows = (await session.execute(members_stmt)).mappings().all()

        resolved_target = target_semester or _default_target_semester(resolved_source)
        return SemesterTransferPreview(
            group_id=group_row["id"],
            group_name=group_row["navn"],
            source_semester=resolved_source,
            source_semester_label=format_semester_code(resolved_source),
            target_semester=resolved_target,
            target_semester_label=format_semester_code(resolved_target),
            candidates=[
                SemesterTransferCandidate(
                    volunteer_id=row["id_personal"],
                    volunteer_name=row["volunteer_name"] or f"Volunteer {row['id_personal']}",
                    role_id=row["id_verv"],
                    role_name=row["verv_navn"],
                    contract_signed=row["signert_kontrakt"],
                    source_history_id=row["id"],
                )
                for row in member_rows
            ],
        )

    async def apply_transfer(self, group_id: int, target_semester: int, entries: list[SemesterTransferEntry]) -> int:
        async with get_session_factory()() as session:
            group_exists = await session.scalar(select(grupper.c.id).where(grupper.c.id == group_id).limit(1))
        if group_exists is None:
            raise SemesterTransferGroupNotFoundError(f"Group {group_id} was not found.")
        if not entries:
            return 0
        volunteer_ids = [entry.volunteer_id for entry in entries]
        if not volunteer_ids:
            return 0
        existing_stmt = (
            select(historie.c.id_personal)
            .where(historie.c.id_gruppe == group_id)
            .where(historie.c.semester == target_semester)
            .where(historie.c.id_personal.in_(volunteer_ids))
        )
        async with get_session_factory()() as session:
            existing_volunteers = {
                row["id_personal"]
                for row in (await session.execute(existing_stmt)).mappings().all()
            }
        values = [
            {
                "id_personal": entry.volunteer_id,
                "id_gruppe": group_id,
                "id_verv": entry.role_id,
                "semester": target_semester,
                "signert_kontrakt": entry.contract_signed,
            }
            for entry in entries
            if entry.volunteer_id not in existing_volunteers
        ]
        if not values:
            return 0
        async with get_session_factory()() as session:
            async with session.begin():
                await session.execute(insert(historie), values)
        return len(values)


def _default_target_semester(source_semester: int) -> int:
    current = get_current_semester_code()
    return current if current > source_semester else get_next_semester_code(source_semester)
