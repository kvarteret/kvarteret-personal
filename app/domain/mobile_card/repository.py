from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import logging
from time import perf_counter

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repository import SqlAlchemyRepository
from app.db.tables import groups, role_assignments, volunteer_records, volunteer_photos, assignment_roles
from app.domain.mobile_card.tables import mobile_card_access_codes
from app.observability import log_operation_timing

logger = logging.getLogger("app.performance")


@dataclass(slots=True)
class MobileCardRoleSnapshot:
    name: str
    group: str
    group_id: int
    discount_level: int | None
    pingvin_points: int
    signed_contract: bool


@dataclass(slots=True)
class MobileCardRoleHistorySnapshot:
    name: str
    group: str
    group_id: int
    discount_level: int | None
    pingvin_points: int
    signed_contract: bool
    semester: int
    is_active: bool


@dataclass(slots=True)
class MobileCardSnapshot:
    volunteer_id: int
    first_name: str
    last_name: str
    birth_date: date | None
    created_at: datetime
    photo_path: str | None
    pingvin_points: int
    active_roles: list[MobileCardRoleSnapshot]
    role_history: list[MobileCardRoleHistorySnapshot] = field(default_factory=list)


class MobileCardRepository(SqlAlchemyRepository):
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None = None
    ) -> None:
        super().__init__(session_factory=session_factory)

    async def find_volunteers_by_email(self, email: str) -> list[dict]:
        stmt = (
            select(
                volunteer_records.c.id,
                volunteer_records.c.first_name,
                volunteer_records.c.last_name,
                mobile_card_access_codes.c.code_hash,
                mobile_card_access_codes.c.created_at,
            )
            .select_from(
                volunteer_records.outerjoin(
                    mobile_card_access_codes,
                    mobile_card_access_codes.c.volunteer_id == volunteer_records.c.id,
                )
            )
            .where(func.lower(func.coalesce(volunteer_records.c.email, "")) == email)
            .order_by(volunteer_records.c.id.asc())
        )
        return await self.fetch_all_mappings(stmt)

    async def store_access_code(
        self, *, volunteer_id: int, access_code: str, created_at: datetime
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(mobile_card_access_codes)
                    .where(mobile_card_access_codes.c.volunteer_id == volunteer_id)
                    .values(
                        code_hash=access_code,
                        created_at=created_at,
                    )
                )

    async def find_volunteer_by_email_and_code(
        self,
        *,
        email: str,
        access_code: str,
        expires_after: datetime,
    ) -> dict | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = (
                    (
                        await session.execute(
                            select(volunteer_records.c.id)
                            .select_from(
                                volunteer_records.join(
                                    mobile_card_access_codes,
                                    mobile_card_access_codes.c.volunteer_id == volunteer_records.c.id,
                                )
                            )
                            .where(func.lower(func.coalesce(volunteer_records.c.email, "")) == email)
                            .where(mobile_card_access_codes.c.code_hash == access_code)
                            .where(mobile_card_access_codes.c.created_at >= expires_after)
                            .limit(1)
                        )
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    return None
                await session.execute(
                    update(mobile_card_access_codes)
                    .where(mobile_card_access_codes.c.volunteer_id == row["id"])
                    .values(code_hash=None, created_at=None)
                )
                return dict(row)

    async def fetch_card_snapshot(
        self,
        *,
        volunteer_id: int,
        semester_code: int,
        include_role_history: bool = False,
    ) -> MobileCardSnapshot | None:
        started_at = perf_counter()
        points_stmt = (
            select(func.coalesce(func.sum(assignment_roles.c.penguin_points), 0))
            .select_from(role_assignments.outerjoin(assignment_roles, assignment_roles.c.id == role_assignments.c.role_id))
            .where(role_assignments.c.volunteer_id == volunteer_id)
            .scalar_subquery()
        )
        snapshot_stmt = (
            select(
                volunteer_records.c.id,
                volunteer_records.c.first_name,
                volunteer_records.c.last_name,
                volunteer_records.c.birth_date,
                volunteer_records.c.created_at,
                volunteer_photos.c.sha1,
                volunteer_photos.c.filetype,
                points_stmt.label("pingvin_points"),
                assignment_roles.c.name.label("verv_navn"),
                groups.c.name.label("gruppe_navn"),
                role_assignments.c.group_id.label("gruppe_id"),
                groups.c.discount_tier,
                assignment_roles.c.penguin_points.label("pingvin_poeng"),
                role_assignments.c.contract_signed,
            )
            .select_from(
                volunteer_records.outerjoin(
                    volunteer_photos, volunteer_photos.c.volunteer_id == volunteer_records.c.id
                )
                .outerjoin(
                    role_assignments,
                    (role_assignments.c.volunteer_id == volunteer_records.c.id)
                    & (role_assignments.c.semester == semester_code),
                )
                .outerjoin(assignment_roles, assignment_roles.c.id == role_assignments.c.role_id)
                .outerjoin(groups, groups.c.id == role_assignments.c.group_id)
            )
            .where(volunteer_records.c.id == volunteer_id)
            .order_by(groups.c.name.asc().nullslast(), assignment_roles.c.name.asc().nullslast())
        )
        history_stmt = (
            select(
                role_assignments.c.id,
                role_assignments.c.semester,
                role_assignments.c.group_id.label("gruppe_id"),
                groups.c.name.label("gruppe_navn"),
                assignment_roles.c.name.label("verv_navn"),
                groups.c.discount_tier,
                assignment_roles.c.penguin_points.label("pingvin_poeng"),
                role_assignments.c.contract_signed,
            )
            .select_from(
                role_assignments.join(groups, groups.c.id == role_assignments.c.group_id).outerjoin(
                    assignment_roles,
                    assignment_roles.c.id == role_assignments.c.role_id,
                )
            )
            .where(role_assignments.c.volunteer_id == volunteer_id)
            .order_by(role_assignments.c.semester.desc(), role_assignments.c.id.desc())
        )
        async with self.session_factory() as session:
            rows = list((await session.execute(snapshot_stmt)).mappings().all())
            history_rows = (
                list((await session.execute(history_stmt)).mappings().all())
                if include_role_history
                else []
            )
            log_operation_timing(
                logger,
                operation="mobile_card.snapshot",
                started_at=started_at,
                details={"volunteer_id": volunteer_id, "semester_code": semester_code},
            )
            if not rows:
                return None
            person_row = rows[0]

        photo_path = None
        if person_row["sha1"] and person_row["filetype"]:
            photo_path = f"{person_row['sha1']}.{person_row['filetype']}"

        return MobileCardSnapshot(
            volunteer_id=person_row["id"],
            first_name=person_row["first_name"] or "",
            last_name=person_row["last_name"],
            birth_date=person_row["birth_date"],
            created_at=person_row["created_at"],
            photo_path=photo_path,
            pingvin_points=int(person_row["pingvin_points"] or 0),
            active_roles=[
                MobileCardRoleSnapshot(
                    name=row["verv_navn"],
                    group=row["gruppe_navn"],
                    group_id=row["gruppe_id"],
                    discount_level=row["discount_tier"],
                    pingvin_points=int(row["pingvin_poeng"] or 0),
                    signed_contract=row["contract_signed"],
                )
                for row in rows
                if row["verv_navn"] is not None and row["gruppe_navn"] is not None
            ],
            role_history=[
                MobileCardRoleHistorySnapshot(
                    name=row["verv_navn"] or "",
                    group=row["gruppe_navn"],
                    group_id=row["gruppe_id"],
                    discount_level=row["discount_tier"],
                    pingvin_points=int(row["pingvin_poeng"] or 0),
                    signed_contract=row["contract_signed"],
                    semester=int(row["semester"]),
                    is_active=int(row["semester"]) == semester_code,
                )
                for row in history_rows
                if row["gruppe_navn"] is not None
            ],
        )
