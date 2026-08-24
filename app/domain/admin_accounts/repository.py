from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.auth.roles import UserRole
from app.db.repository import SqlAlchemyRepository
from app.domain.admin_accounts.tables import group_admin_memberships, user_accounts, web_sessions
from app.domain.spotify.tables import integration_tokens
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
                user_accounts.c.username,
                user_accounts.c.email,
                user_accounts.c.display_name,
                user_accounts.c.role,
                user_accounts.c.last_login,
                func.count(group_admin_memberships.c.group_id).label(
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
                user_accounts.c.username,
                user_accounts.c.email,
                user_accounts.c.display_name,
                user_accounts.c.role,
                user_accounts.c.last_login,
                user_accounts.c.created_at,
                user_accounts.c.migrated_at,
                user_accounts.c.onboarding_status,
                user_accounts.c.onboarding_last_sent_at,
                user_accounts.c.activated_at,
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
            username=row["username"],
            email=row["email"],
            display_name=row.get("display_name"),
            role=UserRole(row["role"]),
            last_login=coerce_datetime(row.get("last_login")),
            created_at=require_datetime(row["created_at"]),
            migrated_at=coerce_datetime(row.get("migrated_at")),
            group_admin_group_ids=memberships.get(row["auth_user_id"], []),
            onboarding_status=row.get("onboarding_status") or "active",
            onboarding_last_sent_at=coerce_datetime(row.get("onboarding_last_sent_at")),
            activated_at=coerce_datetime(row.get("activated_at")),
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
        self,
        *,
        username: str,
        email: str,
        exclude_user_account_id: int | None = None,
    ) -> bool:
        conditions = [
            func.lower(user_accounts.c.username) == username.strip().lower(),
            func.lower(user_accounts.c.email) == email.strip().lower(),
        ]
        stmt = (
            select(user_accounts.c.id)
            .where(or_(*conditions))
            .limit(1)
        )
        if exclude_user_account_id is not None:
            stmt = stmt.where(user_accounts.c.id != exclude_user_account_id)
        return await self.fetch_scalar(stmt) is not None

    async def find_user_account_id_by_email(self, email: str) -> int | None:
        stmt = (
            select(user_accounts.c.id)
            .where(func.lower(user_accounts.c.email) == email.strip().lower())
            .limit(1)
        )
        user_account_id = await self.fetch_scalar(stmt)
        return int(user_account_id) if user_account_id is not None else None

    async def claim_onboarding_email(
        self, user_account_id: int, *, cooldown_seconds: int = 60
    ) -> bool:
        cutoff = datetime.now(UTC) - timedelta(seconds=max(0, cooldown_seconds))
        stmt = update(user_accounts).where(
            user_accounts.c.id == user_account_id,
            or_(
                user_accounts.c.onboarding_last_sent_at.is_(None),
                user_accounts.c.onboarding_last_sent_at <= cutoff,
            ),
        )
        result = await self.session.execute(
            stmt.values(
                onboarding_last_sent_at=func.current_timestamp(),
                updated_at=func.current_timestamp(),
            )
        )
        return bool(result.rowcount)

    async def mark_onboarding_complete(self, auth_user_id: UUID) -> None:
        await self.execute(
            update(user_accounts)
            .where(user_accounts.c.auth_user_id == auth_user_id)
            .values(
                onboarding_status="active",
                activated_at=func.coalesce(
                    user_accounts.c.activated_at, func.current_timestamp()
                ),
                updated_at=func.current_timestamp(),
            )
        )

    async def find_user_account_id_by_username(self, username: str) -> int | None:
        stmt = (
            select(user_accounts.c.id)
            .where(func.lower(user_accounts.c.username) == username.strip().lower())
            .limit(1)
        )
        user_account_id = await self.fetch_scalar(stmt)
        return int(user_account_id) if user_account_id is not None else None

    async def create_admin_account(
        self,
        *,
        auth_user_id: UUID,
        username: str,
        email: str,
        display_name: str | None,
        role: UserRole,
    ) -> int | None:
        try:
            async with self.session.begin_nested():
                row = await self.execute_one_mapping(
                    insert(user_accounts)
                    .values(
                        auth_user_id=auth_user_id,
                        username=username,
                        email=email,
                        display_name=display_name,
                        role=role.value,
                        onboarding_status="pending",
                        created_at=func.current_timestamp(),
                        updated_at=func.current_timestamp(),
                    )
                    .returning(user_accounts.c.id)
                )
                return int(row["id"])
        except IntegrityError:
            # A concurrent request may have won the unique identity/email/
            # username race. The service reconciles the committed row below.
            return None

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

        await delete_account(self.session)

    async def _load_group_admin_ids(
        self, auth_user_ids: list[UUID]
    ) -> dict[UUID, list[int]]:
        if not auth_user_ids:
            return {}
        stmt = (
            select(
                group_admin_memberships.c.auth_user_id,
                group_admin_memberships.c.group_id,
            )
            .where(group_admin_memberships.c.auth_user_id.in_(auth_user_ids))
            .order_by(
                group_admin_memberships.c.auth_user_id.asc(),
                group_admin_memberships.c.group_id.asc(),
            )
        )
        memberships: dict[UUID, list[int]] = {
            auth_user_id: [] for auth_user_id in auth_user_ids
        }
        for row in await self.fetch_all_mappings(stmt):
            memberships.setdefault(row["auth_user_id"], []).append(row["group_id"])
        return memberships
