from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import (
    case,
    delete,
    func,
    insert,
    select,
    update,
)

from app.db.tables import (
    group_admin_memberships,
    grupper,
    grupper_kurs_kobling,
    historie,
    verv,
)
from app.domain.groups.queries import (
    GroupBreakdownItem,
    GroupDetail,
    GroupListItem,
    GroupMemberCount,
    GroupMemberItem,
    GroupPositionItem,
    GroupsQueries,
    OrgSemesterDetailed,
    SemesterGroup,
    SemesterRetentionStats,
    SemesterStats,
)
from app.infrastructure.formatting.semester import get_current_semester_code

__all__ = [
    "GroupBreakdownItem",
    "GroupDeleteBlockedError",
    "GroupDetail",
    "GroupHistoryNotFoundError",
    "GroupListItem",
    "GroupMemberCount",
    "GroupMemberItem",
    "GroupPositionItem",
    "GroupRoleDeleteBlockedError",
    "GroupsService",
    "GroupsServiceProtocol",
    "OrgSemesterDetailed",
    "SemesterGroup",
    "SemesterRetentionStats",
    "SemesterStats",
]


class GroupDeleteBlockedError(ValueError):
    def __init__(self, blockers: list[str]) -> None:
        super().__init__("Group deletion is blocked.")
        self.blockers = blockers


class GroupRoleDeleteBlockedError(ValueError):
    def __init__(self, blockers: list[str]) -> None:
        super().__init__("Group role deletion is blocked.")
        self.blockers = blockers


class GroupHistoryNotFoundError(ValueError):
    pass



class GroupsServiceProtocol(Protocol):
    async def list_groups(
        self, query: str | None = None, limit: int = 100
    ) -> list[GroupListItem]: ...
    async def get_group_detail(self, group_id: int) -> GroupDetail | None: ...
    async def get_group_history_by_semester(
        self, group_id: int
    ) -> list[SemesterGroup]: ...
    async def get_group_semester_stats(self, group_id: int) -> list[SemesterStats]: ...
    async def get_current_group_member_counts(self) -> list[GroupMemberCount]: ...
    async def get_org_stats_detailed(self) -> list[OrgSemesterDetailed]: ...
    async def get_org_retention_stats(self) -> list[SemesterRetentionStats]: ...
    async def get_group_retention_stats(
        self, group_id: int
    ) -> list[SemesterRetentionStats]: ...
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
    async def archive_group(self, group_id: int) -> bool: ...
    async def delete_group(self, group_id: int) -> bool: ...
    async def create_group_role(
        self, group_id: int, *, role_name: str, pingvin_points: int
    ) -> int | None: ...
    async def update_group_role(
        self, group_id: int, role_id: int, *, role_name: str, pingvin_points: int
    ) -> bool: ...
    async def delete_group_role(self, group_id: int, role_id: int) -> bool: ...
    async def delete_group_history_entry(
        self, group_id: int, history_id: int
    ) -> None: ...




class GroupsService(GroupsQueries):
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
                beskrivelse=(
                    description.strip() if description and description.strip() else None
                ),
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
                    beskrivelse=(
                        description.strip()
                        if description and description.strip()
                        else None
                    ),
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

    async def archive_group(self, group_id: int) -> bool:
        current_semester = get_current_semester_code()

        async def callback(session):
            result = await session.execute(
                update(grupper)
                .where(grupper.c.id == group_id)
                .values(
                    aktiv=False,
                    aktiv_til_og_med=case(
                        (
                            grupper.c.aktiv_til_og_med > current_semester,
                            current_semester,
                        ),
                        else_=grupper.c.aktiv_til_og_med,
                    ),
                )
                .returning(grupper.c.id)
            )
            row = result.first()
            return row[0] if row is not None else None

        archived_group_id = await self.execute_in_transaction(callback)
        return archived_group_id == group_id

    async def delete_group(self, group_id: int) -> bool:
        blockers = await self._get_group_delete_blockers(group_id)
        if blockers:
            raise GroupDeleteBlockedError(blockers)

        async def callback(session):
            await session.execute(
                delete(group_admin_memberships).where(
                    group_admin_memberships.c.gruppe_id == group_id
                )
            )
            await session.execute(
                delete(grupper_kurs_kobling).where(
                    grupper_kurs_kobling.c.id_gruppe == group_id
                )
            )
            await session.execute(delete(verv).where(verv.c.id_gruppe == group_id))
            result = await session.execute(
                delete(grupper).where(grupper.c.id == group_id).returning(grupper.c.id)
            )
            row = result.first()
            return row[0] if row is not None else None

        deleted_group_id = await self.execute_in_transaction(callback)
        return deleted_group_id == group_id

    async def create_group_role(
        self, group_id: int, *, role_name: str, pingvin_points: int
    ) -> int | None:
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

    async def update_group_role(
        self, group_id: int, role_id: int, *, role_name: str, pingvin_points: int
    ) -> bool:
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
                delete(verv)
                .where(verv.c.id == role_id, verv.c.id_gruppe == group_id)
                .returning(verv.c.id)
            )
            row = result.first()
            return row[0] if row is not None else None

        deleted_role_id = await self.execute_in_transaction(callback)
        return deleted_role_id == role_id

    async def delete_group_history_entry(self, group_id: int, history_id: int) -> None:
        row = await self.fetch_one_mapping(
            select(historie.c.id, historie.c.id_gruppe).where(
                historie.c.id == history_id
            )
        )
        if row is None or row["id_gruppe"] != group_id:
            raise GroupHistoryNotFoundError(
                f"Group history entry {history_id} was not found."
            )
        await self.execute(delete(historie).where(historie.c.id == history_id))

    async def _get_group_role_delete_blockers(
        self, group_id: int, role_id: int
    ) -> list[str]:
        role_exists = await self.fetch_scalar(
            select(func.count())
            .select_from(verv)
            .where(verv.c.id == role_id, verv.c.id_gruppe == group_id)
        )
        if not role_exists:
            return []
        history_count = await self.fetch_scalar(
            select(func.count())
            .select_from(historie)
            .where(historie.c.id_verv == role_id, historie.c.id_gruppe == group_id)
        )
        blockers: list[str] = []
        if history_count:
            blockers.append("Vervet har medlemmer og kan ikke slettes.")
        return blockers
