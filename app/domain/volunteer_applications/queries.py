"""Read side of the volunteer application module.

Admin list, the recent-registrations feed, and the cached pending
count. ``VolunteerApplicationsService`` inherits this class and adds
the lifecycle writes; the workflow's record loads stay with the write
side in the repository.
"""

from __future__ import annotations

from sqlalchemy import func, literal, or_, select

from app.cache import TTLCache
from app.db.repository import SqlAlchemyRepository
from app.domain.groups.tables import groups
from app.domain.role_assignments.tables import assignment_roles, role_assignments
from app.domain.volunteer_applications.tables import (
    volunteer_application_invites,
    volunteer_application_submissions,
)
from app.domain.volunteers.tables import volunteer_photos, volunteer_records
from app.domain.volunteer_applications.models import (
    RecentVolunteerRegistrationItem,
    RecentVolunteerRegistrationPage,
    VolunteerApplicationListItem,
    build_full_name,
)
from app.shared.semester import format_semester_code


class VolunteerApplicationsQueries(SqlAlchemyRepository):
    def __init__(
        self,
        repository=None,
        pending_count_cache_ttl_seconds: int = 30,
    ) -> None:
        self.repository = repository
        self._pending_count_cache: TTLCache[str, int] = TTLCache(
            ttl_seconds=pending_count_cache_ttl_seconds,
            max_entries=1,
        )

    async def list_volunteer_applications(
        self,
        query: str | None = None,
        application_status: str | None = None,
        group_id: int | None = None,
    ) -> list[VolunteerApplicationListItem]:
        accepted_group = groups.alias("accepted_group")
        first_choice_group = groups.alias("first_choice_group")
        second_choice_group = groups.alias("second_choice_group")
        accepted_role = assignment_roles.alias("accepted_role")
        stmt = (
            select(
                volunteer_application_invites.c.id,
                volunteer_application_invites.c.token,
                volunteer_application_invites.c.email,
                volunteer_application_invites.c.created_at,
                volunteer_application_invites.c.source,
                volunteer_application_invites.c.status,
                volunteer_application_invites.c.initial_group_id,
                volunteer_application_invites.c.initial_role_id,
                volunteer_application_invites.c.first_choice_group_id,
                volunteer_application_invites.c.second_choice_group_id,
                volunteer_application_invites.c.trial_shift_attended,
                volunteer_application_invites.c.trial_started_at,
                volunteer_application_invites.c.trial_ends_at,
                volunteer_application_invites.c.full_profile_submitted_at,
                volunteer_application_invites.c.promoted_volunteer_id,
                volunteer_application_invites.c.promoted_at,
                volunteer_application_submissions.c.id.label("pending_volunteer_id"),
                volunteer_application_submissions.c.first_name,
                volunteer_application_submissions.c.last_name,
                volunteer_application_submissions.c.phone,
                volunteer_application_submissions.c.studiested,
                volunteer_application_submissions.c.bakgrunn,
                accepted_group.c.name.label("initial_group_name"),
                accepted_role.c.name.label("initial_role_name"),
                func.coalesce(
                    volunteer_application_invites.c.first_choice_label,
                    first_choice_group.c.name,
                ).label("first_choice_group_name"),
                func.coalesce(
                    volunteer_application_invites.c.second_choice_label,
                    second_choice_group.c.name,
                ).label("second_choice_group_name"),
            )
            .select_from(
                volunteer_application_invites.outerjoin(
                    volunteer_application_submissions, volunteer_application_submissions.c.invite_id == volunteer_application_invites.c.id
                )
                .outerjoin(
                    accepted_group,
                    accepted_group.c.id == volunteer_application_invites.c.initial_group_id,
                )
                .outerjoin(
                    accepted_role, accepted_role.c.id == volunteer_application_invites.c.initial_role_id
                )
                .outerjoin(
                    first_choice_group,
                    first_choice_group.c.id == volunteer_application_invites.c.first_choice_group_id,
                )
                .outerjoin(
                    second_choice_group,
                    second_choice_group.c.id == volunteer_application_invites.c.second_choice_group_id,
                )
            )
            .order_by(
                volunteer_application_invites.c.created_at.desc(),
                volunteer_application_invites.c.id.desc(),
            )
        )
        allowed_statuses = {"new", "contacted", "trial", "volunteer", "not_volunteer"}
        if application_status == "active" or (
            application_status is not None
            and application_status not in allowed_statuses
            and application_status != ""
        ):
            stmt = stmt.where(
                volunteer_application_invites.c.status.notin_(
                    ("volunteer", "not_volunteer")
                )
            )
        elif application_status in allowed_statuses:
            stmt = stmt.where(volunteer_application_invites.c.status == application_status)
        if group_id is not None:
            stmt = stmt.where(
                or_(
                    volunteer_application_invites.c.initial_group_id == group_id,
                    volunteer_application_invites.c.first_choice_group_id == group_id,
                    volunteer_application_invites.c.second_choice_group_id == group_id,
                )
            )
        normalized_query = (query or "").strip().casefold()
        if normalized_query:
            search_text = literal("")
            for column in (
                volunteer_application_submissions.c.first_name,
                volunteer_application_submissions.c.last_name,
                volunteer_application_invites.c.email,
                volunteer_application_submissions.c.phone,
                volunteer_application_submissions.c.studiested,
            ):
                search_text = search_text + func.coalesce(column, "") + literal(" ")
            stmt = stmt.where(
                func.lower(search_text).contains(normalized_query, autoescape=True)
            )
        session = self.session
        rows = (await session.execute(stmt)).mappings().all()
        friend_relationships = await self.repository.list_friend_relationships(
            [row["id"] for row in rows]
        )
        return [
            VolunteerApplicationListItem(
                registration_id=row["id"],
                token=row["token"],
                email=row["email"],
                created_at=row["created_at"],
                submitted=row["full_profile_submitted_at"] is not None,
                source=row["source"],
                status=row["status"],
                pending_volunteer_id=row["pending_volunteer_id"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                phone=row["phone"],
                study_institution=row["studiested"],
                background_details=row["bakgrunn"],
                initial_group_id=row["initial_group_id"],
                initial_group_name=row["initial_group_name"],
                initial_role_id=row["initial_role_id"],
                initial_role_name=row["initial_role_name"],
                first_choice_group_id=row["first_choice_group_id"],
                first_choice_group_name=row["first_choice_group_name"],
                second_choice_group_id=row["second_choice_group_id"],
                second_choice_group_name=row["second_choice_group_name"],
                trial_shift_attended=bool(row["trial_shift_attended"]),
                trial_started_at=row["trial_started_at"],
                trial_ends_at=row["trial_ends_at"],
                promoted_volunteer_id=row["promoted_volunteer_id"],
                promoted_at=row["promoted_at"],
                invited_by=friend_relationships[row["id"]][0],
                friend_invitees=friend_relationships[row["id"]][1],
            )
            for row in rows
        ]

    async def list_recent_volunteer_registrations(
        self,
        *,
        limit: int,
        before_volunteer_id: int | None = None,
    ) -> list[dict]:
        latest_assignment_rank = (
            func.row_number()
            .over(
                partition_by=role_assignments.c.volunteer_id,
                order_by=(role_assignments.c.id.desc(),),
            )
            .label("assignment_rank")
        )
        latest_assignment_rows = (
            select(
                role_assignments.c.volunteer_id.label("volunteer_id"),
                role_assignments.c.group_id.label("latest_group_id"),
                role_assignments.c.role_id.label("latest_role_id"),
                role_assignments.c.semester.label("latest_semester_code"),
                latest_assignment_rank,
            )
        ).subquery()
        latest_assignment = (
            select(
                latest_assignment_rows.c.volunteer_id,
                latest_assignment_rows.c.latest_group_id,
                latest_assignment_rows.c.latest_role_id,
                latest_assignment_rows.c.latest_semester_code,
            ).where(latest_assignment_rows.c.assignment_rank == 1)
        ).subquery()
        stmt = (
            select(
                volunteer_records.c.id,
                volunteer_records.c.first_name,
                volunteer_records.c.last_name,
                volunteer_records.c.email,
                volunteer_records.c.phone,
                volunteer_records.c.created_at,
                latest_assignment.c.latest_semester_code,
                groups.c.name.label("latest_group_name"),
                assignment_roles.c.name.label("latest_role_name"),
                volunteer_photos.c.sha1.label("photo_sha1"),
                volunteer_photos.c.filetype.label("photo_filetype"),
                volunteer_application_invites.c.id.label("registration_id"),
            )
            .select_from(
                volunteer_records.outerjoin(
                    latest_assignment, latest_assignment.c.volunteer_id == volunteer_records.c.id
                )
                .outerjoin(groups, groups.c.id == latest_assignment.c.latest_group_id)
                .outerjoin(assignment_roles, assignment_roles.c.id == latest_assignment.c.latest_role_id)
                .outerjoin(
                    volunteer_photos, volunteer_photos.c.volunteer_id == volunteer_records.c.id
                )
                .outerjoin(
                    volunteer_application_invites, volunteer_application_invites.c.promoted_volunteer_id == volunteer_records.c.id
                )
            )
            .order_by(volunteer_records.c.id.desc())
            .limit(limit)
        )
        if before_volunteer_id is not None:
            stmt = stmt.where(volunteer_records.c.id < before_volunteer_id)
        session = self.session
        rows = (await session.execute(stmt)).mappings().all()
        return [dict(row) for row in rows]

    async def list_recent_volunteer_registrations_page(
        self,
        limit: int = 20,
        cursor: str | None = None,
    ) -> RecentVolunteerRegistrationPage:
        safe_limit = max(1, min(limit, 100))
        before_volunteer_id = _parse_recent_registration_cursor(cursor)
        rows = await self.list_recent_volunteer_registrations(
            limit=safe_limit + 1,
            before_volunteer_id=before_volunteer_id,
        )
        has_more = len(rows) > safe_limit
        visible_rows = rows[:safe_limit]
        items = [self._map_recent_registration_row(row) for row in visible_rows]
        return RecentVolunteerRegistrationPage(
            items=items,
            limit=safe_limit,
            cursor=cursor,
            next_cursor=str(visible_rows[-1]["id"]) if has_more and visible_rows else None,
        )

    def _map_recent_registration_row(self, row: dict) -> RecentVolunteerRegistrationItem:
        return RecentVolunteerRegistrationItem(
            volunteer_id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            full_name=build_full_name(row["first_name"], row["last_name"]),
            email=row["email"],
            phone=row["phone"],
            created_at=row["created_at"],
            latest_group_name=row["latest_group_name"],
            latest_role_name=row["latest_role_name"],
            latest_semester_code=row["latest_semester_code"],
            latest_semester_label=(
                format_semester_code(row["latest_semester_code"])
                if row["latest_semester_code"] is not None
                else None
            ),
            photo_url=(
                self.repository.media_token_service.build_photo_media_url(
                    f"{row['photo_sha1']}.{row['photo_filetype']}"
                )
                if row.get("photo_sha1") and row.get("photo_filetype") and self.repository.media_token_service is not None
                else None
            ),
            registration_id=row.get("registration_id"),
        )

    async def count_pending_volunteer_applications(self) -> int:
        cached_count = self._pending_count_cache.get("pending-count")
        if cached_count is not None:
            return cached_count
        pending_count = await self.repository.count_pending_volunteer_applications()
        self._pending_count_cache.set("pending-count", pending_count)
        return pending_count

    def _invalidate_pending_count_cache(self) -> None:
        self._pending_count_cache.pop("pending-count")

    def invalidate_pending_count_cache(self) -> None:
        """Public entry point for event handlers to invalidate the pending count cache."""
        self._invalidate_pending_count_cache()


def _parse_recent_registration_cursor(cursor: str | None) -> int | None:
    if cursor is None:
        return None
    stripped = cursor.strip()
    if not stripped:
        return None
    try:
        volunteer_id = int(stripped)
    except ValueError:
        return None
    return volunteer_id if volunteer_id > 0 else None
