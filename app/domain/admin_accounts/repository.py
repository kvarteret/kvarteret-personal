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
from app.domain.volunteers.tables import volunteer_records, volunteer_photos
from app.domain.groups.tables import groups
from app.domain.role_assignments.tables import role_assignments
from app.shared.semester import get_current_semester_code

from app.domain.admin_accounts.models import AdminAccountDetail, AdminAccountListItem

logger = logging.getLogger("app.performance")


class AdminAccountsRepository(SqlAlchemyRepository):
    async def application_group_filter(self, account_id: int, semester: int) -> list[int] | None:
        account = await self.get_admin_account_detail(account_id)
        if account is None:
            return []
        associations = []
        if account.volunteer_id:
            associations = await self.fetch_all_mappings(
                select(groups.c.id, groups.c.name).join(role_assignments, role_assignments.c.group_id == groups.c.id)
                .where(role_assignments.c.volunteer_id == account.volunteer_id, role_assignments.c.semester == semester, groups.c.is_active.is_(True))
            )
        if any(row["name"].strip().casefold() in {"administrasjonen", "hovedstyret"} for row in associations):
            return None
        active_ids = {row["id"] for row in await self.access_groups()}
        group_ids = sorted(({row["id"] for row in associations} | set(account.group_admin_group_ids)) & active_ids)
        # Old shared admin logins can remain unlinked during the transition.
        if not account.volunteer_id and account.role == UserRole.ADMIN and not group_ids:
            return None
        return group_ids

    async def group_admin_groups(self, auth_user_id: UUID):
        return await self.fetch_all_mappings(
            select(groups.c.slug, groups.c.name)
            .join(group_admin_memberships, group_admin_memberships.c.group_id == groups.c.id)
            .where(group_admin_memberships.c.auth_user_id == auth_user_id, groups.c.is_active.is_(True))
            .order_by(groups.c.name)
        )

    async def access_groups(self):
        return await self.fetch_all_mappings(select(groups.c.id, groups.c.name).where(groups.c.is_active.is_(True)).order_by(groups.c.name))

    async def volunteer_identity(self, volunteer_id: int):
        return await self.fetch_first_mapping(select(volunteer_records).where(volunteer_records.c.id == volunteer_id))

    async def account_for_volunteer(self, volunteer_id: int):
        return await self.fetch_scalar(select(user_accounts.c.id).where(user_accounts.c.volunteer_id == volunteer_id))

    async def configure_access(self, account_id: int, volunteer_id: int, role: UserRole, group_ids: list[int]):
        account = await self.get_admin_account_detail(account_id)
        volunteer = await self.volunteer_identity(volunteer_id)
        if account is None or volunteer is None:
            raise ValueError('Konto eller frivillig finnes ikke.')
        if account.is_legacy_account:
            raise ValueError('Velg den frivilliges individuelle konto. Gammel innlogging beholdes under overgangen.')
        if (volunteer['email'] or '').strip().lower() != account.email.strip().lower():
            raise ValueError('Kontoens e-post må samsvare med den frivilliges personlige e-post.')
        linked = await self.account_for_volunteer(volunteer_id)
        if linked is not None and linked != account_id:
            raise ValueError('Den frivillige er allerede koblet til en annen konto.')
        valid_groups = {g['id'] for g in await self.access_groups()}
        if set(group_ids) - valid_groups or (role == UserRole.GROUP_ADMIN and not group_ids):
            raise ValueError('Velg minst én gyldig gruppe for gruppeadmin.')
        await self.execute(update(user_accounts).where(user_accounts.c.id == account_id).values(volunteer_id=volunteer_id, role=role.value, updated_at=func.current_timestamp()))
        await self.execute(delete(group_admin_memberships).where(group_admin_memberships.c.auth_user_id == account.auth_user_id))
        if role == UserRole.GROUP_ADMIN:
            for gid in sorted(set(group_ids)):
                await self.execute(insert(group_admin_memberships).values(auth_user_id=account.auth_user_id, group_id=gid, created_at=func.current_timestamp()))
        # Re-authenticate after permission changes so cached sessions cannot
        # retain the previous role or impersonation privileges.
        await self.execute(delete(web_sessions).where(or_(
            web_sessions.c.user_account_id == account_id,
            web_sessions.c.impersonator_user_account_id == account_id,
        )))

    async def list_admin_accounts(
        self, query: str | None = None, limit: int = 100, account_type: str = "all"
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
                user_accounts.c.volunteer_id,
                user_accounts.c.is_legacy_account,
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
                user_accounts.c.volunteer_id,
                user_accounts.c.is_legacy_account,
            )
            .where(user_accounts.c.is_legacy_account.is_(False))
            .order_by(user_accounts.c.role.asc(), user_accounts.c.username.asc())
            .limit(limit)
        )
        if account_type == "personal":
            stmt = stmt.where(user_accounts.c.volunteer_id.is_not(None), user_accounts.c.is_legacy_account.is_(False))
        elif account_type == "legacy":
            stmt = stmt.where(user_accounts.c.is_legacy_account.is_(True))
        elif account_type == "unlinked":
            stmt = stmt.where(user_accounts.c.volunteer_id.is_(None), user_accounts.c.is_legacy_account.is_(False))
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
        memberships = await self._load_group_admin_ids([row["auth_user_id"] for row in rows])
        volunteer_ids = [row["volunteer_id"] for row in rows if row["volunteer_id"]]
        photos = await self.fetch_all_mappings(select(volunteer_photos).where(volunteer_photos.c.volunteer_id.in_(volunteer_ids))) if volunteer_ids else []
        photo_paths = {photo["volunteer_id"]: f"{photo['sha1']}.{photo['filetype']}" for photo in photos}
        associations = await self.fetch_all_mappings(
            select(role_assignments.c.volunteer_id, groups.c.id, groups.c.name)
            .join(groups, groups.c.id == role_assignments.c.group_id)
            .where(role_assignments.c.volunteer_id.in_(volunteer_ids),
                   role_assignments.c.semester == get_current_semester_code(), groups.c.is_active.is_(True))
        ) if volunteer_ids else []
        current_groups = {}
        for association in associations:
            current_groups.setdefault(association["volunteer_id"], {})[association["id"]] = association["name"]
        active_groups = {group["id"]: group["name"] for group in await self.access_groups()}
        associated_groups = {}
        for row in rows:
            grants = set(memberships.get(row["auth_user_id"], [])) & active_groups.keys()
            names = {**current_groups.get(row["volunteer_id"], {}), **{gid: active_groups[gid] for gid in grants}}
            if row["role"] == UserRole.ADMIN:
                grants |= {gid for gid, name in names.items() if name.strip().casefold() in {"administrasjonen", "hovedstyret"}}
            associated_groups[row["id"]] = [(gid, name, gid in grants) for gid, name in sorted(names.items(), key=lambda item: item[1].casefold())]
        return [
            AdminAccountListItem(
                user_account_id=row["id"],
                auth_user_id=row["auth_user_id"],
                username=row["username"],
                email=row["email"],
                display_name=row.get("display_name"),
                role=UserRole(row["role"]),
                last_login=coerce_datetime(row.get("last_login")),
                group_admin_group_ids=memberships.get(row["auth_user_id"], []),
                associated_groups=associated_groups[row["id"]],
                photo_path=photo_paths.get(row["volunteer_id"]),
                volunteer_id=row["volunteer_id"],
                is_legacy_account=row["is_legacy_account"],
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
                user_accounts.c.volunteer_id,
                user_accounts.c.is_legacy_account,
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
            volunteer_id=row.get('volunteer_id'),
            is_legacy_account=row.get('is_legacy_account', False),
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
