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
    groups,
    group_course_requirements,
    role_assignments,
    assignment_roles,
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
            insert(groups)
            .values(
                name=name.strip(),
                description=(
                    description.strip() if description and description.strip() else None
                ),
                is_active=active,
                active_through_semester=active_until_semester,
                parent_group_id=parent_group_id,
                discount_tier=discount_step,
                created_at=datetime.now(UTC),
            )
            .returning(groups.c.id)
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
                update(groups)
                .where(groups.c.id == group_id)
                .values(
                    name=name.strip(),
                    description=(
                        description.strip()
                        if description and description.strip()
                        else None
                    ),
                    is_active=active,
                    active_through_semester=active_until_semester,
                    parent_group_id=parent_group_id,
                    discount_tier=discount_step,
                )
                .returning(groups.c.id)
            )
            row = result.first()
            return row[0] if row is not None else None

        updated_group_id = await callback(self.session)
        return updated_group_id == group_id

    async def archive_group(self, group_id: int) -> bool:
        current_semester = get_current_semester_code()

        async def callback(session):
            result = await session.execute(
                update(groups)
                .where(groups.c.id == group_id)
                .values(
                    is_active=False,
                    active_through_semester=case(
                        (
                            groups.c.active_through_semester > current_semester,
                            current_semester,
                        ),
                        else_=groups.c.active_through_semester,
                    ),
                )
                .returning(groups.c.id)
            )
            row = result.first()
            return row[0] if row is not None else None

        archived_group_id = await callback(self.session)
        return archived_group_id == group_id

    async def delete_group(self, group_id: int) -> bool:
        blockers = await self._get_group_delete_blockers(group_id)
        if blockers:
            raise GroupDeleteBlockedError(blockers)

        async def callback(session):
            await session.execute(
                delete(group_admin_memberships).where(
                    group_admin_memberships.c.group_id == group_id
                )
            )
            await session.execute(
                delete(group_course_requirements).where(
                    group_course_requirements.c.group_id == group_id
                )
            )
            await session.execute(delete(assignment_roles).where(assignment_roles.c.group_id == group_id))
            result = await session.execute(
                delete(groups).where(groups.c.id == group_id).returning(groups.c.id)
            )
            row = result.first()
            return row[0] if row is not None else None

        deleted_group_id = await callback(self.session)
        return deleted_group_id == group_id

    async def create_group_role(
        self, group_id: int, *, role_name: str, pingvin_points: int
    ) -> int | None:
        normalized_role_name = role_name.strip()
        if not normalized_role_name:
            raise ValueError("Role name is required.")
        row = await self.execute_one_mapping(
            insert(assignment_roles)
            .values(
                group_id=group_id,
                name=normalized_role_name,
                penguin_points=pingvin_points,
            )
            .returning(assignment_roles.c.id)
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
                update(assignment_roles)
                .where(assignment_roles.c.id == role_id, assignment_roles.c.group_id == group_id)
                .values(
                    name=normalized_role_name,
                    penguin_points=pingvin_points,
                )
                .returning(assignment_roles.c.id)
            )
            row = result.first()
            return row[0] if row is not None else None

        updated_role_id = await callback(self.session)
        return updated_role_id == role_id

    async def delete_group_role(self, group_id: int, role_id: int) -> bool:
        blockers = await self._get_group_role_delete_blockers(group_id, role_id)
        if blockers:
            raise GroupRoleDeleteBlockedError(blockers)

        async def callback(session):
            result = await session.execute(
                delete(assignment_roles)
                .where(assignment_roles.c.id == role_id, assignment_roles.c.group_id == group_id)
                .returning(assignment_roles.c.id)
            )
            row = result.first()
            return row[0] if row is not None else None

        deleted_role_id = await callback(self.session)
        return deleted_role_id == role_id

    async def delete_group_history_entry(self, group_id: int, history_id: int) -> None:
        row = await self.fetch_one_mapping(
            select(role_assignments.c.id, role_assignments.c.group_id).where(
                role_assignments.c.id == history_id
            )
        )
        if row is None or row["group_id"] != group_id:
            raise GroupHistoryNotFoundError(
                f"Group history entry {history_id} was not found."
            )
        await self.execute(delete(role_assignments).where(role_assignments.c.id == history_id))

    async def _get_group_role_delete_blockers(
        self, group_id: int, role_id: int
    ) -> list[str]:
        role_exists = await self.fetch_scalar(
            select(func.count())
            .select_from(assignment_roles)
            .where(assignment_roles.c.id == role_id, assignment_roles.c.group_id == group_id)
        )
        if not role_exists:
            return []
        history_count = await self.fetch_scalar(
            select(func.count())
            .select_from(role_assignments)
            .where(role_assignments.c.role_id == role_id, role_assignments.c.group_id == group_id)
        )
        blockers: list[str] = []
        if history_count:
            blockers.append("Vervet har medlemmer og kan ikke slettes.")
        return blockers
