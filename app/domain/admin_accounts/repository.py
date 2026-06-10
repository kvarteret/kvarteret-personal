from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.roles import UserRole
from app.db.repository import SqlAlchemyRepository
from app.db.tables import (
    group_admin_memberships,
    integration_tokens,
    user_accounts,
    web_sessions,
)
from app.shared.coercion import coerce_datetime, require_datetime

from app.domain.admin_accounts.models import AdminAccountDetail, AdminAccountListItem

logger = logging.getLogger("app.performance")


class AdminAccountsRepository(SqlAlchemyRepository):
    async def list_admin_accounts(
        self, query: str | None = None, limit: int = 100
    ) -> list[AdminAccountListItem]:
        stmt = (
            select(
                user_accounts.c.id,
                user_accounts.c.auth_user_id,
                user_accounts.c.legacy_user_id,
                user_accounts.c.username,
                user_accounts.c.email,
                user_accounts.c.display_name,
                user_accounts.c.role,
                user_accounts.c.last_login,
                func.count(group_admin_memberships.c.gruppe_id).label(
                    "group_admin_group_count"
                ),
            )
            .select_from(
                user_accounts.outerjoin(
                    group_admin_memberships,
                    group_admin_memberships.c.auth_user_id
                    == user_accounts.c.auth_user_id,
                )
            )
            .group_by(
                user_accounts.c.id,
                user_accounts.c.auth_user_id,
                user_accounts.c.legacy_user_id,
                user_accounts.c.username,
                user_accounts.c.email,
                user_accounts.c.display_name,
                user_accounts.c.role,
                user_accounts.c.last_login,
            )
            .order_by(user_accounts.c.role.asc(), user_accounts.c.username.asc())
            .limit(limit)
        )
        if query and query.strip():
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    user_accounts.c.username.ilike(pattern),
                    user_accounts.c.email.ilike(pattern),
                    user_accounts.c.display_name.ilike(pattern),
                )
            )
        rows = await self.fetch_all_mappings(stmt)
        return [
            AdminAccountListItem(
                user_account_id=row["id"],
                auth_user_id=row["auth_user_id"],
                legacy_user_id=row.get("legacy_user_id"),
                username=row["username"],
                email=row["email"],
                display_name=row.get("display_name"),
                role=UserRole(row["role"]),
                last_login=coerce_datetime(row.get("last_login")),
                group_admin_group_ids=[],
                group_admin_group_count=row["group_admin_group_count"] or 0,
            )
            for row in rows
        ]

    async def get_admin_account_detail(
        self, user_account_id: int
    ) -> AdminAccountDetail | None:
        stmt = (
            select(
                user_accounts.c.id,
                user_accounts.c.auth_user_id,
                user_accounts.c.legacy_user_id,
                user_accounts.c.username,
                user_accounts.c.email,
                user_accounts.c.display_name,
                user_accounts.c.role,
                user_accounts.c.last_login,
                user_accounts.c.created_at,
                user_accounts.c.migrated_at,
            )
            .where(user_accounts.c.id == user_account_id)
            .limit(1)
        )
        row = await self.fetch_first_mapping(stmt)
        if row is None:
            return None
        memberships = await self._load_group_admin_ids([row["auth_user_id"]])
        return AdminAccountDetail(
            user_account_id=row["id"],
            auth_user_id=row["auth_user_id"],
            legacy_user_id=row.get("legacy_user_id"),
            username=row["username"],
            email=row["email"],
            display_name=row.get("display_name"),
            role=UserRole(row["role"]),
            last_login=coerce_datetime(row.get("last_login")),
            created_at=require_datetime(row["created_at"]),
            migrated_at=coerce_datetime(row.get("migrated_at")),
            group_admin_group_ids=memberships.get(row["auth_user_id"], []),
        )

    async def find_user_account_id_by_auth_user_id(
        self, auth_user_id: UUID
    ) -> int | None:
        stmt = (
            select(user_accounts.c.id)
            .where(user_accounts.c.auth_user_id == auth_user_id)
            .limit(1)
        )
        user_account_id = await self.fetch_scalar(stmt)
        return int(user_account_id) if user_account_id is not None else None

    async def check_username_or_email_exists(
        self, *, username: str, email: str
    ) -> bool:
        stmt = (
            select(user_accounts.c.id)
            .where(
                or_(
                    user_accounts.c.username == username,
                    user_accounts.c.email == email,
                )
            )
            .limit(1)
        )
        return await self.fetch_scalar(stmt) is not None

    async def create_admin_account(
        self,
        *,
        auth_user_id: UUID,
        username: str,
        email: str,
        display_name: str | None,
        role: UserRole,
    ) -> int:
        row = await self.execute_one_mapping(
            insert(user_accounts)
            .values(
                auth_user_id=auth_user_id,
                username=username,
                email=email,
                display_name=display_name,
                role=role.value,
                created_at=func.current_timestamp(),
                updated_at=func.current_timestamp(),
            )
            .returning(user_accounts.c.id)
        )
        return row["id"]

    async def update_admin_account(
        self,
        *,
        user_account_id: int,
        username: str,
        email: str,
        display_name: str | None,
        role: UserRole,
    ) -> None:
        await self.execute(
            update(user_accounts)
            .where(user_accounts.c.id == user_account_id)
            .values(
                username=username,
                email=email,
                display_name=display_name,
                role=role.value,
                updated_at=func.current_timestamp(),
            )
        )

    async def delete_admin_account(
        self, *, user_account_id: int, auth_user_id: UUID
    ) -> None:
        async def delete_account(session: AsyncSession) -> None:
            await session.execute(
                update(integration_tokens)
                .where(
                    integration_tokens.c.updated_by_user_account_id == user_account_id
                )
                .values(updated_by_user_account_id=None)
            )
            await session.execute(
                delete(web_sessions).where(
                    or_(
                        web_sessions.c.user_account_id == user_account_id,
                        web_sessions.c.impersonator_user_account_id == user_account_id,
                        web_sessions.c.auth_user_id == auth_user_id,
                        web_sessions.c.impersonator_auth_user_id == auth_user_id,
                    )
                )
            )
            await session.execute(
                delete(group_admin_memberships).where(
                    group_admin_memberships.c.auth_user_id == auth_user_id
                )
            )
            await session.execute(
                delete(user_accounts).where(user_accounts.c.id == user_account_id)
            )

        await self.execute_in_transaction(delete_account)

    async def _load_group_admin_ids(
        self, auth_user_ids: list[UUID]
    ) -> dict[UUID, list[int]]:
        if not auth_user_ids:
            return {}
        stmt = (
            select(
                group_admin_memberships.c.auth_user_id,
                group_admin_memberships.c.gruppe_id,
            )
            .where(group_admin_memberships.c.auth_user_id.in_(auth_user_ids))
            .order_by(
                group_admin_memberships.c.auth_user_id.asc(),
                group_admin_memberships.c.gruppe_id.asc(),
            )
        )
        memberships: dict[UUID, list[int]] = {
            auth_user_id: [] for auth_user_id in auth_user_ids
        }
        for row in await self.fetch_all_mappings(stmt):
            memberships.setdefault(row["auth_user_id"], []).append(row["gruppe_id"])
        return memberships
