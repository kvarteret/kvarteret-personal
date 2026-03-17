from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from time import perf_counter
from typing import Protocol

from sqlalchemy import BigInteger, Boolean, Integer, Text, case, delete, distinct, func, insert, literal, or_, select, union_all, update

from app.db.repository import SqlAlchemyRepository
from app.db.tables import group_admin_memberships, grupper, grupper_kurs_kobling, historie, personal, verv
from app.observability import log_operation_timing
from app.services.common import build_full_name, coerce_datetime
from app.services.semester import format_semester_code, get_current_semester_code

logger = logging.getLogger("app.performance")


class GroupDeleteBlockedError(ValueError):
    def __init__(self, blockers: list[str]) -> None:
        super().__init__("Group deletion is blocked.")
        self.blockers = blockers


class GroupRoleDeleteBlockedError(ValueError):
    def __init__(self, blockers: list[str]) -> None:
        super().__init__("Group role deletion is blocked.")
        self.blockers = blockers


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
    assignment_count: int
    delete_blockers: list[str]


@dataclass(slots=True)
class GroupMemberItem:
    history_id: int
    volunteer_id: int
    volunteer_name: str
    role_name: str | None
    semester_code: int
    semester_label: str
    contract_signed: bool


@dataclass(slots=True)
class SemesterGroup:
    semester_code: int
    semester_label: str
    members: list[GroupMemberItem]


@dataclass(slots=True)
class SemesterStats:
    semester_code: int
    semester_label: str
    member_count: int


@dataclass(slots=True)
class GroupMemberCount:
    group_id: int
    group_name: str
    member_count: int


@dataclass(slots=True)
class GroupBreakdownItem:
    group_name: str
    member_count: int


@dataclass(slots=True)
class OrgSemesterDetailed:
    semester_code: int
    semester_label: str
    unique_members: int
    groups: list[GroupBreakdownItem]


@dataclass(slots=True)
class SemesterRetentionStats:
    semester_code: int
    semester_label: str
    total_members: int
    retained_from_prev: int
    new_members: int
    retained_to_next: int
    churned: int


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
    delete_blockers: list[str]


class GroupsServiceProtocol(Protocol):
    async def list_groups(self, query: str | None = None, limit: int = 100) -> list[GroupListItem]: ...
    async def get_group_detail(self, group_id: int) -> GroupDetail | None: ...
    async def get_group_history_by_semester(self, group_id: int) -> list[SemesterGroup]: ...
    async def get_group_semester_stats(self, group_id: int) -> list[SemesterStats]: ...
    async def get_current_group_member_counts(self) -> list[GroupMemberCount]: ...
    async def get_org_stats_detailed(self) -> list[OrgSemesterDetailed]: ...
    async def get_org_retention_stats(self) -> list[SemesterRetentionStats]: ...
    async def get_group_retention_stats(self, group_id: int) -> list[SemesterRetentionStats]: ...
    async def create_group(
        self,
        *,
        name: str,
        description: str | None,
        active: bool,
        active_until_semester: int,
        parent_group_id: int | None,
        discount_step: int | None,
    ) -> int: ...
    async def update_group(
        self,
        group_id: int,
        *,
        name: str,
        description: str | None,
        active: bool,
        active_until_semester: int,
        parent_group_id: int | None,
        discount_step: int | None,
    ) -> bool: ...
    async def delete_group(self, group_id: int) -> bool: ...
    async def create_group_role(self, group_id: int, *, role_name: str, pingvin_points: int) -> int | None: ...
    async def update_group_role(self, group_id: int, role_id: int, *, role_name: str, pingvin_points: int) -> bool: ...
    async def delete_group_role(self, group_id: int, role_id: int) -> bool: ...


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
        role_assignment_counts = (
            select(
                historie.c.id_verv.label("role_id"),
                func.count().label("assignment_count"),
            )
            .where(historie.c.id_gruppe == group_id, historie.c.id_verv.is_not(None))
            .group_by(historie.c.id_verv)
            .subquery()
        )
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
            literal(None, type_=Integer()).label("position_assignment_count"),
            literal(None, type_=BigInteger()).label("history_id"),
            literal(None, type_=BigInteger()).label("volunteer_id"),
            literal(None, type_=Text()).label("volunteer_first_name"),
            literal(None, type_=Text()).label("volunteer_last_name"),
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
            func.coalesce(role_assignment_counts.c.assignment_count, 0).label("position_assignment_count"),
            literal(None, type_=BigInteger()).label("history_id"),
            literal(None, type_=BigInteger()).label("volunteer_id"),
            literal(None, type_=Text()).label("volunteer_first_name"),
            literal(None, type_=Text()).label("volunteer_last_name"),
            literal(None, type_=Text()).label("member_role_name"),
            literal(None, type_=Integer()).label("member_semester"),
            literal(None, type_=Boolean()).label("member_contract_signed"),
        ).select_from(
            verv.outerjoin(role_assignment_counts, role_assignment_counts.c.role_id == verv.c.id)
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
            literal(None, type_=Integer()).label("position_assignment_count"),
            recent_members.c.id.label("history_id"),
            recent_members.c.id_personal.label("volunteer_id"),
            recent_members.c.fornavn.label("volunteer_first_name"),
            recent_members.c.etternavn.label("volunteer_last_name"),
            recent_members.c.role_name.label("member_role_name"),
            recent_members.c.semester.label("member_semester"),
            recent_members.c.signert_kontrakt.label("member_contract_signed"),
        )
        rows = await self.fetch_all_mappings(union_all(group_select, positions_select, members_select))
        log_operation_timing(logger, operation="groups.detail", started_at=started_at, details={"group_id": group_id})
        group_row = next((row for row in rows if row["row_type"] == "group"), None)
        if group_row is None:
            return None
        delete_blockers = await self._get_group_delete_blockers(group_id)
        positions: list[GroupPositionItem] = []
        seen_positions: set[int] = set()
        members: list[GroupMemberItem] = []
        seen_members: set[int] = set()
        for row in rows:
            if row["row_type"] == "position" and row["position_id"] is not None and row["position_id"] not in seen_positions:
                seen_positions.add(row["position_id"])
                assignment_count = row["position_assignment_count"] or 0
                delete_blockers = ["Vervet har medlemmer og kan ikke slettes."] if assignment_count else []
                positions.append(
                    GroupPositionItem(
                        role_id=row["position_id"],
                        role_name=row["position_name"],
                        pingvin_points=row["position_points"],
                        assignment_count=assignment_count,
                        delete_blockers=delete_blockers,
                    )
                )
            if row["row_type"] == "member" and row["history_id"] is not None and row["history_id"] not in seen_members:
                seen_members.add(row["history_id"])
                members.append(
                    GroupMemberItem(
                        history_id=row["history_id"],
                        volunteer_id=row["volunteer_id"],
                        volunteer_name=build_full_name(row.get("volunteer_first_name"), row.get("volunteer_last_name")),
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
            delete_blockers=delete_blockers,
        )

    async def get_group_history_by_semester(self, group_id: int) -> list[SemesterGroup]:
        stmt = (
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
            .order_by(historie.c.semester.desc(), personal.c.etternavn.asc(), personal.c.fornavn.asc(), historie.c.id.asc())
        )
        rows = await self.fetch_all_mappings(stmt)
        grouped_members: dict[int, list[GroupMemberItem]] = defaultdict(list)
        for row in rows:
            semester_code = row["semester"]
            grouped_members[semester_code].append(
                GroupMemberItem(
                    history_id=row["id"],
                    volunteer_id=row["id_personal"],
                    volunteer_name=build_full_name(row.get("fornavn"), row.get("etternavn")),
                    role_name=row.get("role_name"),
                    semester_code=semester_code,
                    semester_label=format_semester_code(semester_code) or str(semester_code),
                    contract_signed=row["signert_kontrakt"],
                )
            )
        return [
            SemesterGroup(
                semester_code=semester_code,
                semester_label=format_semester_code(semester_code) or str(semester_code),
                members=members,
            )
            for semester_code, members in sorted(grouped_members.items(), reverse=True)
        ]

    async def get_group_semester_stats(self, group_id: int) -> list[SemesterStats]:
        stmt = (
            select(
                historie.c.semester,
                func.count(distinct(historie.c.id_personal)).label("member_count"),
            )
            .where(historie.c.id_gruppe == group_id)
            .group_by(historie.c.semester)
            .order_by(historie.c.semester.asc())
        )
        rows = await self.fetch_all_mappings(stmt)
        return [
            SemesterStats(
                semester_code=row["semester"],
                semester_label=format_semester_code(row["semester"]) or str(row["semester"]),
                member_count=row["member_count"],
            )
            for row in rows
        ]

    async def get_current_group_member_counts(self) -> list[GroupMemberCount]:
        current_semester = get_current_semester_code()
        stmt = (
            select(
                grupper.c.id,
                grupper.c.navn,
                func.count(distinct(historie.c.id_personal)).label("member_count"),
            )
            .select_from(grupper.join(historie, historie.c.id_gruppe == grupper.c.id))
            .where(historie.c.semester == current_semester)
            .group_by(grupper.c.id, grupper.c.navn)
            .order_by(func.count(distinct(historie.c.id_personal)).desc(), grupper.c.navn.asc())
            .limit(25)
        )
        rows = await self.fetch_all_mappings(stmt)
        return [
            GroupMemberCount(
                group_id=row["id"],
                group_name=row["navn"],
                member_count=row["member_count"],
            )
            for row in rows
        ]

    async def get_org_stats_detailed(self) -> list[OrgSemesterDetailed]:
        org_stmt = (
            select(
                historie.c.semester,
                func.count(distinct(historie.c.id_personal)).label("unique_members"),
            )
            .group_by(historie.c.semester)
            .order_by(historie.c.semester.asc())
        )
        breakdown_stmt = (
            select(
                historie.c.semester,
                grupper.c.navn.label("group_name"),
                func.count(distinct(historie.c.id_personal)).label("member_count"),
            )
            .select_from(historie.join(grupper, grupper.c.id == historie.c.id_gruppe))
            .group_by(historie.c.semester, grupper.c.id, grupper.c.navn)
            .order_by(historie.c.semester.asc(), func.count(distinct(historie.c.id_personal)).desc(), grupper.c.navn.asc())
        )
        org_rows = await self.fetch_all_mappings(org_stmt)
        breakdown_rows = await self.fetch_all_mappings(breakdown_stmt)
        grouped_breakdown: dict[int, list[GroupBreakdownItem]] = defaultdict(list)
        for row in breakdown_rows:
            grouped_breakdown[row["semester"]].append(
                GroupBreakdownItem(
                    group_name=row["group_name"],
                    member_count=row["member_count"],
                )
            )
        return [
            OrgSemesterDetailed(
                semester_code=row["semester"],
                semester_label=format_semester_code(row["semester"]) or str(row["semester"]),
                unique_members=row["unique_members"],
                groups=grouped_breakdown.get(row["semester"], []),
            )
            for row in org_rows
        ]

    async def get_org_retention_stats(self) -> list[SemesterRetentionStats]:
        history_current = historie.alias("history_current")
        history_prev = historie.alias("history_prev")
        history_next = historie.alias("history_next")
        previous_semester = case(
            (history_current.c.semester % 10 == 1, history_current.c.semester - 9),
            else_=history_current.c.semester - 1,
        )
        next_semester = case(
            (history_current.c.semester % 10 == 1, history_current.c.semester + 1),
            else_=history_current.c.semester + 9,
        )
        stmt = (
            select(
                history_current.c.semester,
                func.count(distinct(history_current.c.id_personal)).label("total_members"),
                func.count(
                    distinct(case((history_prev.c.id_personal.is_not(None), history_current.c.id_personal)))
                ).label("retained_from_prev"),
                func.count(
                    distinct(case((history_next.c.id_personal.is_not(None), history_current.c.id_personal)))
                ).label("retained_to_next"),
            )
            .select_from(
                history_current.outerjoin(
                    history_prev,
                    (history_prev.c.id_personal == history_current.c.id_personal)
                    & (history_prev.c.semester == previous_semester),
                ).outerjoin(
                    history_next,
                    (history_next.c.id_personal == history_current.c.id_personal)
                    & (history_next.c.semester == next_semester),
                )
            )
            .group_by(history_current.c.semester)
            .order_by(history_current.c.semester.asc())
        )
        rows = await self.fetch_all_mappings(stmt)
        return [_map_retention_stat_row(row) for row in rows]

    async def get_group_retention_stats(self, group_id: int) -> list[SemesterRetentionStats]:
        history_current = historie.alias("history_current")
        history_prev = historie.alias("history_prev")
        history_next = historie.alias("history_next")
        previous_semester = case(
            (history_current.c.semester % 10 == 1, history_current.c.semester - 9),
            else_=history_current.c.semester - 1,
        )
        next_semester = case(
            (history_current.c.semester % 10 == 1, history_current.c.semester + 1),
            else_=history_current.c.semester + 9,
        )
        stmt = (
            select(
                history_current.c.semester,
                func.count(distinct(history_current.c.id_personal)).label("total_members"),
                func.count(
                    distinct(case((history_prev.c.id_personal.is_not(None), history_current.c.id_personal)))
                ).label("retained_from_prev"),
                func.count(
                    distinct(case((history_next.c.id_personal.is_not(None), history_current.c.id_personal)))
                ).label("retained_to_next"),
            )
            .select_from(
                history_current.outerjoin(
                    history_prev,
                    (history_prev.c.id_personal == history_current.c.id_personal)
                    & (history_prev.c.id_gruppe == history_current.c.id_gruppe)
                    & (history_prev.c.semester == previous_semester),
                ).outerjoin(
                    history_next,
                    (history_next.c.id_personal == history_current.c.id_personal)
                    & (history_next.c.id_gruppe == history_current.c.id_gruppe)
                    & (history_next.c.semester == next_semester),
                )
            )
            .where(history_current.c.id_gruppe == group_id)
            .group_by(history_current.c.semester)
            .order_by(history_current.c.semester.asc())
        )
        rows = await self.fetch_all_mappings(stmt)
        return [_map_retention_stat_row(row) for row in rows]

    async def create_group(
        self,
        *,
        name: str,
        description: str | None,
        active: bool,
        active_until_semester: int,
        parent_group_id: int | None,
        discount_step: int | None,
    ) -> int:
        row = await self.execute_one_mapping(
            insert(grupper)
            .values(
                navn=name.strip(),
                beskrivelse=(description.strip() if description and description.strip() else None),
                aktiv=active,
                aktiv_til_og_med=active_until_semester,
                id_overgruppe=parent_group_id,
                rabatt_trinn=discount_step,
                opprettet=datetime.now(UTC),
            )
            .returning(grupper.c.id)
        )
        return row["id"]

    async def update_group(
        self,
        group_id: int,
        *,
        name: str,
        description: str | None,
        active: bool,
        active_until_semester: int,
        parent_group_id: int | None,
        discount_step: int | None,
    ) -> bool:
        async def callback(session):
            result = await session.execute(
                update(grupper)
                .where(grupper.c.id == group_id)
                .values(
                    navn=name.strip(),
                    beskrivelse=(description.strip() if description and description.strip() else None),
                    aktiv=active,
                    aktiv_til_og_med=active_until_semester,
                    id_overgruppe=parent_group_id,
                    rabatt_trinn=discount_step,
                )
                .returning(grupper.c.id)
            )
            row = result.first()
            return row[0] if row is not None else None

        updated_group_id = await self.execute_in_transaction(callback)
        return updated_group_id == group_id

    async def delete_group(self, group_id: int) -> bool:
        blockers = await self._get_group_delete_blockers(group_id)
        if blockers:
            raise GroupDeleteBlockedError(blockers)

        async def callback(session):
            await session.execute(delete(group_admin_memberships).where(group_admin_memberships.c.gruppe_id == group_id))
            await session.execute(delete(grupper_kurs_kobling).where(grupper_kurs_kobling.c.id_gruppe == group_id))
            await session.execute(delete(verv).where(verv.c.id_gruppe == group_id))
            result = await session.execute(delete(grupper).where(grupper.c.id == group_id).returning(grupper.c.id))
            row = result.first()
            return row[0] if row is not None else None

        deleted_group_id = await self.execute_in_transaction(callback)
        return deleted_group_id == group_id

    async def create_group_role(self, group_id: int, *, role_name: str, pingvin_points: int) -> int | None:
        normalized_role_name = role_name.strip()
        if not normalized_role_name:
            raise ValueError("Role name is required.")
        row = await self.execute_one_mapping(
            insert(verv)
            .values(
                id_gruppe=group_id,
                verv=normalized_role_name,
                pingvinpoeng=pingvin_points,
            )
            .returning(verv.c.id)
        )
        return row["id"] if row is not None else None

    async def update_group_role(self, group_id: int, role_id: int, *, role_name: str, pingvin_points: int) -> bool:
        normalized_role_name = role_name.strip()
        if not normalized_role_name:
            raise ValueError("Role name is required.")

        async def callback(session):
            result = await session.execute(
                update(verv)
                .where(verv.c.id == role_id, verv.c.id_gruppe == group_id)
                .values(
                    verv=normalized_role_name,
                    pingvinpoeng=pingvin_points,
                )
                .returning(verv.c.id)
            )
            row = result.first()
            return row[0] if row is not None else None

        updated_role_id = await self.execute_in_transaction(callback)
        return updated_role_id == role_id

    async def delete_group_role(self, group_id: int, role_id: int) -> bool:
        blockers = await self._get_group_role_delete_blockers(group_id, role_id)
        if blockers:
            raise GroupRoleDeleteBlockedError(blockers)

        async def callback(session):
            result = await session.execute(
                delete(verv).where(verv.c.id == role_id, verv.c.id_gruppe == group_id).returning(verv.c.id)
            )
            row = result.first()
            return row[0] if row is not None else None

        deleted_role_id = await self.execute_in_transaction(callback)
        return deleted_role_id == role_id

    async def _get_group_delete_blockers(self, group_id: int) -> list[str]:
        child_group_count = await self.fetch_scalar(
            select(func.count()).select_from(grupper).where(grupper.c.id_overgruppe == group_id)
        )
        history_count = await self.fetch_scalar(
            select(func.count()).select_from(historie).where(historie.c.id_gruppe == group_id)
        )
        blockers: list[str] = []
        if child_group_count:
            blockers.append("Gruppen har undergrupper.")
        if history_count:
            blockers.append("Gruppen har historikk og kan ikke slettes.")
        return blockers

    async def _get_group_role_delete_blockers(self, group_id: int, role_id: int) -> list[str]:
        role_exists = await self.fetch_scalar(
            select(func.count()).select_from(verv).where(verv.c.id == role_id, verv.c.id_gruppe == group_id)
        )
        if not role_exists:
            return []
        history_count = await self.fetch_scalar(
            select(func.count()).select_from(historie).where(historie.c.id_verv == role_id, historie.c.id_gruppe == group_id)
        )
        blockers: list[str] = []
        if history_count:
            blockers.append("Vervet har medlemmer og kan ikke slettes.")
        return blockers


def _map_retention_stat_row(row) -> SemesterRetentionStats:
    total_members = row["total_members"]
    retained_from_prev = row["retained_from_prev"]
    retained_to_next = row["retained_to_next"]
    return SemesterRetentionStats(
        semester_code=row["semester"],
        semester_label=format_semester_code(row["semester"]) or str(row["semester"]),
        total_members=total_members,
        retained_from_prev=retained_from_prev,
        new_members=total_members - retained_from_prev,
        retained_to_next=retained_to_next,
        churned=total_members - retained_to_next,
    )
