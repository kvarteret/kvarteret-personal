from __future__ import annotations

from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Protocol

from sqlalchemy import BigInteger, Boolean, Integer, Text, literal, or_, select, union_all

from app.db.repository import SqlAlchemyRepository
from app.db.tables import grupper, historie, personal, verv
from app.observability import log_operation_timing
from app.services.common import build_full_name, coerce_datetime
from app.services.semester import format_semester_code

logger = logging.getLogger("app.performance")


@dataclass(slots=True)
class GroupListItem:
    group_id: int
    name: str
    description: str | None
    active: bool
    active_until_semester: int
    parent_group_id: int | None
    discount_step: int | None


@dataclass(slots=True)
class GroupPositionItem:
    role_id: int
    role_name: str | None
    pingvin_points: int


@dataclass(slots=True)
class GroupMemberItem:
    history_id: int
    person_id: int
    person_name: str
    role_name: str | None
    semester_code: int
    semester_label: str
    contract_signed: bool


@dataclass(slots=True)
class GroupDetail:
    group_id: int
    name: str
    description: str | None
    active: bool
    active_until_semester: int
    active_until_label: str | None
    parent_group_id: int | None
    discount_step: int | None
    created_at: datetime | None
    positions: list[GroupPositionItem]
    recent_members: list[GroupMemberItem]


class GroupsServiceProtocol(Protocol):
    async def list_groups(self, query: str | None = None, limit: int = 100) -> list[GroupListItem]: ...
    async def get_group_detail(self, group_id: int) -> GroupDetail | None: ...


class GroupsService(SqlAlchemyRepository):
    async def list_groups(self, query: str | None = None, limit: int = 100) -> list[GroupListItem]:
        stmt = (
            select(
                grupper.c.id,
                grupper.c.navn,
                grupper.c.beskrivelse,
                grupper.c.aktiv,
                grupper.c.aktiv_til_og_med,
                grupper.c.id_overgruppe,
                grupper.c.rabatt_trinn,
            )
            .order_by(grupper.c.navn.asc(), grupper.c.id.asc())
            .limit(limit)
        )
        if query and query.strip():
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(or_(grupper.c.navn.ilike(pattern), grupper.c.beskrivelse.ilike(pattern)))
        rows = await self.fetch_all_mappings(stmt)
        return [
            GroupListItem(
                group_id=row["id"],
                name=row["navn"],
                description=row["beskrivelse"],
                active=row["aktiv"],
                active_until_semester=row["aktiv_til_og_med"],
                parent_group_id=row["id_overgruppe"],
                discount_step=row["rabatt_trinn"],
            )
            for row in rows
        ]

    async def get_group_detail(self, group_id: int) -> GroupDetail | None:
        started_at = perf_counter()
        group_select = select(
            literal("group").label("row_type"),
            grupper.c.id.label("group_id"),
            grupper.c.navn.label("group_name"),
            grupper.c.beskrivelse.label("group_description"),
            grupper.c.aktiv.label("group_active"),
            grupper.c.aktiv_til_og_med.label("group_active_until"),
            grupper.c.id_overgruppe.label("group_parent_id"),
            grupper.c.rabatt_trinn.label("group_discount_step"),
            grupper.c.opprettet.label("group_created_at"),
            literal(None, type_=BigInteger()).label("position_id"),
            literal(None, type_=Text()).label("position_name"),
            literal(None, type_=Integer()).label("position_points"),
            literal(None, type_=BigInteger()).label("history_id"),
            literal(None, type_=BigInteger()).label("person_id"),
            literal(None, type_=Text()).label("person_first_name"),
            literal(None, type_=Text()).label("person_last_name"),
            literal(None, type_=Text()).label("member_role_name"),
            literal(None, type_=Integer()).label("member_semester"),
            literal(None, type_=Boolean()).label("member_contract_signed"),
        ).where(grupper.c.id == group_id)
        positions_select = select(
            literal("position").label("row_type"),
            literal(None, type_=BigInteger()).label("group_id"),
            literal(None, type_=Text()).label("group_name"),
            literal(None, type_=Text()).label("group_description"),
            literal(None, type_=Boolean()).label("group_active"),
            literal(None, type_=Integer()).label("group_active_until"),
            literal(None, type_=BigInteger()).label("group_parent_id"),
            literal(None, type_=Integer()).label("group_discount_step"),
            literal(None, type_=grupper.c.opprettet.type).label("group_created_at"),
            verv.c.id.label("position_id"),
            verv.c.verv.label("position_name"),
            verv.c.pingvinpoeng.label("position_points"),
            literal(None, type_=BigInteger()).label("history_id"),
            literal(None, type_=BigInteger()).label("person_id"),
            literal(None, type_=Text()).label("person_first_name"),
            literal(None, type_=Text()).label("person_last_name"),
            literal(None, type_=Text()).label("member_role_name"),
            literal(None, type_=Integer()).label("member_semester"),
            literal(None, type_=Boolean()).label("member_contract_signed"),
        ).where(verv.c.id_gruppe == group_id)
        recent_members = (
            select(
                historie.c.id,
                historie.c.id_personal,
                historie.c.semester,
                historie.c.signert_kontrakt,
                personal.c.fornavn,
                personal.c.etternavn,
                verv.c.verv.label("role_name"),
            )
            .select_from(
                historie.join(personal, personal.c.id == historie.c.id_personal).outerjoin(verv, verv.c.id == historie.c.id_verv)
            )
            .where(historie.c.id_gruppe == group_id)
            .order_by(historie.c.semester.desc(), historie.c.id.desc())
            .limit(20)
            .subquery()
        )
        members_select = select(
            literal("member").label("row_type"),
            literal(None, type_=BigInteger()).label("group_id"),
            literal(None, type_=Text()).label("group_name"),
            literal(None, type_=Text()).label("group_description"),
            literal(None, type_=Boolean()).label("group_active"),
            literal(None, type_=Integer()).label("group_active_until"),
            literal(None, type_=BigInteger()).label("group_parent_id"),
            literal(None, type_=Integer()).label("group_discount_step"),
            literal(None, type_=grupper.c.opprettet.type).label("group_created_at"),
            literal(None, type_=BigInteger()).label("position_id"),
            literal(None, type_=Text()).label("position_name"),
            literal(None, type_=Integer()).label("position_points"),
            recent_members.c.id.label("history_id"),
            recent_members.c.id_personal.label("person_id"),
            recent_members.c.fornavn.label("person_first_name"),
            recent_members.c.etternavn.label("person_last_name"),
            recent_members.c.role_name.label("member_role_name"),
            recent_members.c.semester.label("member_semester"),
            recent_members.c.signert_kontrakt.label("member_contract_signed"),
        )
        rows = await self.fetch_all_mappings(union_all(group_select, positions_select, members_select))
        log_operation_timing(logger, operation="groups.detail", started_at=started_at, details={"group_id": group_id})
        group_row = next((row for row in rows if row["row_type"] == "group"), None)
        if group_row is None:
            return None
        positions: list[GroupPositionItem] = []
        seen_positions: set[int] = set()
        members: list[GroupMemberItem] = []
        seen_members: set[int] = set()
        for row in rows:
            if row["row_type"] == "position" and row["position_id"] is not None and row["position_id"] not in seen_positions:
                seen_positions.add(row["position_id"])
                positions.append(
                    GroupPositionItem(
                        role_id=row["position_id"],
                        role_name=row["position_name"],
                        pingvin_points=row["position_points"],
                    )
                )
            if row["row_type"] == "member" and row["history_id"] is not None and row["history_id"] not in seen_members:
                seen_members.add(row["history_id"])
                members.append(
                    GroupMemberItem(
                        history_id=row["history_id"],
                        person_id=row["person_id"],
                        person_name=build_full_name(row.get("person_first_name"), row.get("person_last_name")),
                        role_name=row.get("member_role_name"),
                        semester_code=row["member_semester"],
                        semester_label=format_semester_code(row["member_semester"]) or str(row["member_semester"]),
                        contract_signed=row["member_contract_signed"],
                    )
                )
        return GroupDetail(
            group_id=group_row["group_id"],
            name=group_row["group_name"],
            description=group_row["group_description"],
            active=group_row["group_active"],
            active_until_semester=group_row["group_active_until"],
            active_until_label=format_semester_code(group_row["group_active_until"]),
            parent_group_id=group_row["group_parent_id"],
            discount_step=group_row["group_discount_step"],
            created_at=coerce_datetime(group_row.get("group_created_at")),
            positions=sorted(positions, key=lambda item: ((item.role_name or "").lower(), item.role_id)),
            recent_members=sorted(
                members,
                key=lambda item: (item.semester_code, item.history_id),
                reverse=True,
            ),
        )
