from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select, update

from app.db.session import get_session_factory
from app.db.tables import grupper, historie, personal, personal_bilde, verv


@dataclass(slots=True)
class MobileCardRoleSnapshot:
    name: str
    group: str
    discount_level: int | None
    signed_contract: bool


@dataclass(slots=True)
class MobileCardSnapshot:
    person_id: int
    first_name: str
    last_name: str
    birth_date: date | None
    created_at: datetime
    photo_path: str | None
    pingvin_points: int
    active_roles: list[MobileCardRoleSnapshot]


class MobileCardRepository:
    async def find_people_by_email(self, email: str) -> list[dict]:
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
        async with get_session_factory()() as session:
            return list((await session.execute(stmt)).mappings().all())

    async def store_access_code(self, *, person_id: int, access_code: str, created_at: datetime) -> None:
        async with get_session_factory()() as session:
            async with session.begin():
                await session.execute(
                    update(personal)
                    .where(personal.c.id == person_id)
                    .values(
                        internkortaccesstoken=access_code,
                        internkort_access_token_created_at=created_at,
                    )
                )

    async def find_person_by_email_and_code(self, *, email: str, access_code: str, expires_after: datetime) -> dict | None:
        stmt = (
            select(personal.c.id)
            .where(func.lower(func.coalesce(personal.c.epost, "")) == email)
            .where(personal.c.internkortaccesstoken == access_code)
            .where(personal.c.internkort_access_token_created_at.is_not(None))
            .where(personal.c.internkort_access_token_created_at >= expires_after)
            .limit(1)
        )
        async with get_session_factory()() as session:
            return (await session.execute(stmt)).mappings().first()

    async def fetch_card_snapshot(self, *, person_id: int, semester_code: int) -> MobileCardSnapshot | None:
        person_stmt = (
            select(
                personal.c.id,
                personal.c.fornavn,
                personal.c.etternavn,
                personal.c.fodselsdato,
                personal.c.opprettet,
                personal_bilde.c.sha1,
                personal_bilde.c.filetype,
            )
            .select_from(personal.outerjoin(personal_bilde, personal_bilde.c.id_personal == personal.c.id))
            .where(personal.c.id == person_id)
            .limit(1)
        )
        points_stmt = (
            select(func.coalesce(func.sum(verv.c.pingvinpoeng), 0).label("pingvin_points"))
            .select_from(historie.outerjoin(verv, verv.c.id == historie.c.id_verv))
            .where(historie.c.id_personal == person_id)
        )
        active_roles_stmt = (
            select(
                verv.c.verv.label("verv_navn"),
                grupper.c.navn.label("gruppe_navn"),
                grupper.c.rabatt_trinn,
                historie.c.signert_kontrakt,
            )
            .select_from(
                historie.join(verv, verv.c.id == historie.c.id_verv).join(grupper, grupper.c.id == historie.c.id_gruppe)
            )
            .where(historie.c.id_personal == person_id)
            .where(historie.c.semester == semester_code)
            .order_by(grupper.c.navn.asc(), verv.c.verv.asc())
        )
        async with get_session_factory()() as session:
            person_row = (await session.execute(person_stmt)).mappings().first()
            if person_row is None:
                return None
            pingvin_points = int((await session.execute(points_stmt)).scalar_one() or 0)
            active_role_rows = (await session.execute(active_roles_stmt)).mappings().all()

        photo_path = None
        if person_row["sha1"] and person_row["filetype"]:
            photo_path = f"{person_row['sha1']}.{person_row['filetype']}"

        return MobileCardSnapshot(
            person_id=person_row["id"],
            first_name=person_row["fornavn"] or "",
            last_name=person_row["etternavn"],
            birth_date=person_row["fodselsdato"],
            created_at=person_row["opprettet"],
            photo_path=photo_path,
            pingvin_points=pingvin_points,
            active_roles=[
                MobileCardRoleSnapshot(
                    name=row["verv_navn"],
                    group=row["gruppe_navn"],
                    discount_level=row["rabatt_trinn"],
                    signed_contract=row["signert_kontrakt"],
                )
                for row in active_role_rows
            ],
        )
