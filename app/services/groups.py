from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from app.errors import NotConfiguredError
from app.postgrest import PostgrestClient
from app.services.common import build_full_name, coerce_datetime, postgrest_ilike_pattern
from app.services.semester import format_semester_code


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


class GroupsService:
    def __init__(self, postgrest_client: PostgrestClient | None = None) -> None:
        self.postgrest_client = postgrest_client

    async def list_groups(self, query: str | None = None, limit: int = 100) -> list[GroupListItem]:
        if self.postgrest_client is None:
            raise NotConfiguredError("PostgREST-backed group reads are not configured yet.")
        filters: dict[str, str] = {}
        if query and query.strip():
            pattern = postgrest_ilike_pattern(query.strip())
            filters["or"] = f"(navn.ilike.{pattern},beskrivelse.ilike.{pattern})"
        rows = await self.postgrest_client.select_rows(
            "grupper",
            select="id,navn,beskrivelse,aktiv,aktiv_til_og_med,id_overgruppe,rabatt_trinn",
            filters=filters,
            order="navn.asc,id.asc",
            limit=limit,
        )
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
        if self.postgrest_client is None:
            raise NotConfiguredError("PostgREST-backed group reads are not configured yet.")
        group_rows, position_rows, member_rows = await asyncio.gather(
            self.postgrest_client.select_rows(
                "grupper",
                select="id,navn,beskrivelse,aktiv,aktiv_til_og_med,id_overgruppe,rabatt_trinn,opprettet",
                filters={"id": f"eq.{group_id}"},
                limit=1,
            ),
            self.postgrest_client.select_rows(
                "verv",
                select="id,verv,pingvinpoeng",
                filters={"id_gruppe": f"eq.{group_id}"},
                order="verv.asc.nullslast,id.asc",
            ),
            self.postgrest_client.select_rows(
                "historie",
                select="id,semester,signert_kontrakt,personal(id,fornavn,etternavn),verv(verv)",
                filters={"id_gruppe": f"eq.{group_id}"},
                order="semester.desc,id.desc",
                limit=20,
            ),
        )
        if not group_rows:
            return None
        group_row = group_rows[0]
        return GroupDetail(
            group_id=group_row["id"],
            name=group_row["navn"],
            description=group_row["beskrivelse"],
            active=group_row["aktiv"],
            active_until_semester=group_row["aktiv_til_og_med"],
            active_until_label=format_semester_code(group_row["aktiv_til_og_med"]),
            parent_group_id=group_row["id_overgruppe"],
            discount_step=group_row["rabatt_trinn"],
            created_at=coerce_datetime(group_row.get("opprettet")),
            positions=[
                GroupPositionItem(
                    role_id=row["id"],
                    role_name=row["verv"],
                    pingvin_points=row["pingvinpoeng"],
                )
                for row in position_rows
            ],
            recent_members=[
                GroupMemberItem(
                    history_id=row["id"],
                    person_id=row["personal"]["id"],
                    person_name=build_full_name(row["personal"].get("fornavn"), row["personal"].get("etternavn")),
                    role_name=(row.get("verv") or {}).get("verv"),
                    semester_code=row["semester"],
                    semester_label=format_semester_code(row["semester"]) or str(row["semester"]),
                    contract_signed=row["signert_kontrakt"],
                )
                for row in member_rows
            ],
        )
