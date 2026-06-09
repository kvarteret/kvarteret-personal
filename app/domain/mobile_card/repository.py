from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import logging
from time import perf_counter

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repository import SqlAlchemyRepository
from app.db.tables import grupper, historie, personal, personal_bilde, verv
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
                personal.c.id,
                personal.c.fornavn,
                personal.c.etternavn,
                personal.c.internkortaccesstoken,
                personal.c.internkort_access_token_created_at,
            )
            .where(func.lower(func.coalesce(personal.c.epost, "")) == email)
            .order_by(personal.c.id.asc())
        )
        return await self.fetch_all_mappings(stmt)

    async def store_access_code(
        self, *, volunteer_id: int, access_code: str, created_at: datetime
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(personal)
                    .where(personal.c.id == volunteer_id)
                    .values(
                        internkortaccesstoken=access_code,
                        internkort_access_token_created_at=created_at,
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
                            select(personal.c.id)
                            .where(
                                func.lower(func.coalesce(personal.c.epost, "")) == email
                            )
                            .where(personal.c.internkortaccesstoken == access_code)
                            .where(
                                personal.c.internkort_access_token_created_at.is_not(
                                    None
                                )
                            )
                            .where(
                                personal.c.internkort_access_token_created_at
                                >= expires_after
                            )
                            .limit(1)
                        )
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    return None
                await session.execute(
                    update(personal)
                    .where(personal.c.id == row["id"])
                    .values(
                        internkortaccesstoken=None,
                        internkort_access_token_created_at=None,
                    )
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
            select(func.coalesce(func.sum(verv.c.pingvinpoeng), 0))
            .select_from(historie.outerjoin(verv, verv.c.id == historie.c.id_verv))
            .where(historie.c.id_personal == volunteer_id)
            .scalar_subquery()
        )
        snapshot_stmt = (
            select(
                personal.c.id,
                personal.c.fornavn,
                personal.c.etternavn,
                personal.c.fodselsdato,
                personal.c.opprettet,
                personal_bilde.c.sha1,
                personal_bilde.c.filetype,
                points_stmt.label("pingvin_points"),
                verv.c.verv.label("verv_navn"),
                grupper.c.navn.label("gruppe_navn"),
                historie.c.id_gruppe.label("gruppe_id"),
                grupper.c.rabatt_trinn,
                verv.c.pingvinpoeng.label("pingvin_poeng"),
                historie.c.signert_kontrakt,
            )
            .select_from(
                personal.outerjoin(
                    personal_bilde, personal_bilde.c.id_personal == personal.c.id
                )
                .outerjoin(
                    historie,
                    (historie.c.id_personal == personal.c.id)
                    & (historie.c.semester == semester_code),
                )
                .outerjoin(verv, verv.c.id == historie.c.id_verv)
                .outerjoin(grupper, grupper.c.id == historie.c.id_gruppe)
            )
            .where(personal.c.id == volunteer_id)
            .order_by(grupper.c.navn.asc().nullslast(), verv.c.verv.asc().nullslast())
        )
        history_stmt = (
            select(
                historie.c.id,
                historie.c.semester,
                historie.c.id_gruppe.label("gruppe_id"),
                grupper.c.navn.label("gruppe_navn"),
                verv.c.verv.label("verv_navn"),
                grupper.c.rabatt_trinn,
                verv.c.pingvinpoeng.label("pingvin_poeng"),
                historie.c.signert_kontrakt,
            )
            .select_from(
                historie.join(grupper, grupper.c.id == historie.c.id_gruppe).outerjoin(
                    verv,
                    verv.c.id == historie.c.id_verv,
                )
            )
            .where(historie.c.id_personal == volunteer_id)
            .order_by(historie.c.semester.desc(), historie.c.id.desc())
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
            first_name=person_row["fornavn"] or "",
            last_name=person_row["etternavn"],
            birth_date=person_row["fodselsdato"],
            created_at=person_row["opprettet"],
            photo_path=photo_path,
            pingvin_points=int(person_row["pingvin_points"] or 0),
            active_roles=[
                MobileCardRoleSnapshot(
                    name=row["verv_navn"],
                    group=row["gruppe_navn"],
                    group_id=row["gruppe_id"],
                    discount_level=row["rabatt_trinn"],
                    pingvin_points=int(row["pingvin_poeng"] or 0),
                    signed_contract=row["signert_kontrakt"],
                )
                for row in rows
                if row["verv_navn"] is not None and row["gruppe_navn"] is not None
            ],
            role_history=[
                MobileCardRoleHistorySnapshot(
                    name=row["verv_navn"] or "",
                    group=row["gruppe_navn"],
                    group_id=row["gruppe_id"],
                    discount_level=row["rabatt_trinn"],
                    pingvin_points=int(row["pingvin_poeng"] or 0),
                    signed_contract=row["signert_kontrakt"],
                    semester=int(row["semester"]),
                    is_active=int(row["semester"]) == semester_code,
                )
                for row in history_rows
                if row["gruppe_navn"] is not None
            ],
        )
