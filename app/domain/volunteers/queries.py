"""Read side of the volunteers module.

``VolunteersQueries`` holds every list/search/detail read model: the
volunteer list with its keyset cursor, free-text search with offset
cursors, the detail-page panels (shell, role history, course
completions, relations) with their per-volunteer cache, and the
group/role option lists. ``VolunteersService`` inherits this class and
adds the writes, mirroring the groups module's queries/service split.
"""

from __future__ import annotations

import base64
import json
import logging
from time import perf_counter
from typing import Any

from sqlalchemy import Text, and_, func, literal, or_, select, union_all

from app.cache import TTLCache
from app.db.repository import SqlAlchemyRepository
from app.domain.courses.tables import course_completions, courses
from app.domain.groups.tables import groups
from app.domain.role_assignments.tables import assignment_roles, role_assignments
from app.domain.volunteer_applications.tables import (
    volunteer_application_group_members,
    volunteer_application_invites,
)
from app.domain.volunteers.models import (
    AssignmentRoleOption,
    GroupOption,
    RoleAssignmentItem,
    VolunteerCourseCompletionItem,
    VolunteerDetail,
    VolunteerListItem,
    VolunteerListPage,
    VolunteerRelations,
    VolunteerSearchOption,
)
from app.domain.volunteers.search_sql import (
    build_volunteer_search_count_stmt,
    build_volunteer_search_stmt,
    current_active_volunteers_subquery,
    current_discount_level_subquery,
    name_sort_columns,
    pingvin_points_subquery,
    volunteer_list_base_stmt,
)
from app.domain.volunteers.tables import (
    volunteer_cards,
    volunteer_next_of_kin,
    volunteer_photos,
    volunteer_records,
)
from app.media_tokens import MediaTokenService
from app.observability import log_operation_timing
from app.shared.text import normalize_search_query

logger = logging.getLogger("app.performance")


class VolunteersQueries(SqlAlchemyRepository):
    def __init__(
        self,
        media_token_service: MediaTokenService | None = None,
        detail_cache_ttl_seconds: int | None = None,
    ) -> None:
        self.media_token_service = media_token_service
        self.detail_cache_ttl_seconds = detail_cache_ttl_seconds or 300
        # Cache volunteer detail panels independently so one write can
        # invalidate a volunteer's full detail view without forcing every
        # panel to reload on every request.
        self._cache: TTLCache[int, dict[str, Any]] = TTLCache(
            ttl_seconds=self.detail_cache_ttl_seconds,
            max_entries=2048,
        )

    # ── List and search ────────────────────────────────────────────

    async def list_volunteers(
        self, query: str | None = None, limit: int = 50
    ) -> list[VolunteerListItem]:
        return (
            await self.list_volunteers_page(query=query, limit=limit, cursor=None)
        ).items

    async def list_volunteer_search_options(
        self, query: str, limit: int = 10
    ) -> list[VolunteerSearchOption]:
        normalized_query = normalize_search_query(query)
        if not normalized_query or len(normalized_query) < 2:
            return []
        items = await self.list_volunteers(
            query=normalized_query, limit=max(1, min(limit * 2, 100))
        )
        return [
            VolunteerSearchOption(
                volunteer_id=item.volunteer_id,
                full_name=item.full_name,
            )
            for item in sorted(
                items, key=lambda item: (item.full_name.lower(), item.volunteer_id)
            )[:limit]
        ]

    async def count_volunteers(
        self, query: str | None = None, only_active: bool = False
    ) -> int:
        normalized_query = normalize_search_query(query)
        if normalized_query:
            stmt = build_volunteer_search_count_stmt(
                normalized_query=normalized_query, only_active=only_active
            )
            return await self.fetch_scalar(stmt) or 0
        active_volunteers = (
            current_active_volunteers_subquery() if only_active else None
        )
        base = select(volunteer_records.c.id)
        if active_volunteers is not None:
            base = base.select_from(
                volunteer_records.join(
                    active_volunteers,
                    active_volunteers.c.volunteer_id == volunteer_records.c.id,
                )
            )
        stmt = select(func.count()).select_from(base.subquery())
        return await self.fetch_scalar(stmt) or 0

    async def list_volunteers_page(
        self,
        query: str | None = None,
        limit: int = 10,
        cursor: str | None = None,
        only_active: bool = False,
    ) -> VolunteerListPage:
        # Browsing and free-text search need different cursor strategies:
        # browse uses stable name-based cursors, while search falls back to
        # offsets because the query drives ordering.
        started_at = perf_counter()
        safe_limit = max(1, min(limit, 100))
        normalized_query = normalize_search_query(query)
        try:
            if normalized_query:
                page = await self._search_volunteers_page(
                    normalized_query,
                    safe_limit,
                    cursor,
                    only_active=only_active,
                )
            else:
                decoded = _decode_cursor(cursor)
                rows = await self.list_volunteer_page_rows(
                    limit=safe_limit + 1,
                    after_last_name=decoded.get("last_name")
                    if decoded.get("mode") == "browse"
                    else None,
                    after_first_name=decoded.get("first_name")
                    if decoded.get("mode") == "browse"
                    else None,
                    after_volunteer_id=decoded.get("volunteer_id")
                    if decoded.get("mode") == "browse"
                    else None,
                    only_active=only_active,
                )
                has_more = len(rows) > safe_limit
                visible_rows = rows[:safe_limit]
                items = [VolunteerListItem.from_row(row) for row in visible_rows]
                for item, row in zip(items, visible_rows, strict=False):
                    item.photo_url = build_photo_url(
                        self.media_token_service, row.get("sha1"), row.get("filetype")
                    )
                page = VolunteerListPage(
                    items=items,
                    limit=safe_limit,
                    cursor=cursor,
                    next_cursor=_encode_browse_cursor(visible_rows[-1])
                    if has_more and visible_rows
                    else None,
                )
            return page
        finally:
            log_operation_timing(
                logger,
                operation="volunteers.search"
                if normalized_query
                else "volunteers.list",
                started_at=started_at,
                details={
                    "query": normalized_query or "",
                    "limit": safe_limit,
                    "only_active": only_active,
                },
            )

    async def _search_volunteers_page(
        self,
        normalized_query: str,
        limit: int,
        cursor: str | None,
        *,
        only_active: bool = False,
    ) -> VolunteerListPage:
        # Search pagination intentionally uses a bounded offset cursor
        # instead of reusing browse cursors, because query-shaped result
        # sets do not have a stable natural key order.
        decoded = _decode_cursor(cursor)
        offset = int(decoded.get("offset", 0)) if decoded.get("mode") == "search" else 0
        rows = await self.search_volunteers_page(
            normalized_query=normalized_query,
            limit=limit + 1,
            offset=max(0, min(offset, 10_000)),
            only_active=only_active,
        )
        has_more = len(rows) > limit
        visible_rows = rows[:limit]
        items = []
        for row in visible_rows:
            item = VolunteerListItem.from_row(row)
            item.photo_url = build_photo_url(
                self.media_token_service, row.get("sha1"), row.get("filetype")
            )
            items.append(item)
        return VolunteerListPage(
            items=items,
            limit=limit,
            cursor=cursor,
            next_cursor=_encode_cursor({"mode": "search", "offset": offset + limit})
            if has_more
            else None,
        )

    # ── Detail-page panels (cached per volunteer) ──────────────────

    async def get_volunteer_detail(self, volunteer_id: int) -> VolunteerDetail | None:
        started_at = perf_counter()
        cached = self._cache_get(volunteer_id, "shell")
        if cached is not None:
            return cached
        try:
            row = await self.fetch_volunteer_shell_row(volunteer_id)
            if row is None:
                return None
            volunteer = VolunteerDetail.from_row(row)
            volunteer.photo_url = build_photo_url(
                self.media_token_service, row.get("sha1"), row.get("filetype")
            )
            self._cache_set(volunteer_id, "shell", volunteer)
            return volunteer
        finally:
            log_operation_timing(
                logger,
                operation="volunteers.detail.shell",
                started_at=started_at,
                details={"volunteer_id": volunteer_id},
            )

    async def list_role_assignments(
        self, volunteer_id: int, limit: int = 12
    ) -> list[RoleAssignmentItem]:
        started_at = perf_counter()
        cached = self._cache_get(volunteer_id, "history")
        if cached is not None:
            return cached
        try:
            rows = await self.fetch_volunteer_role_assignment_rows(
                volunteer_id, limit=limit
            )
            items = [RoleAssignmentItem.from_row(row) for row in rows]
            self._cache_set(volunteer_id, "history", items)
            return items
        finally:
            log_operation_timing(
                logger,
                operation="volunteers.detail.role_assignments",
                started_at=started_at,
                details={"volunteer_id": volunteer_id},
            )

    async def list_course_completions(
        self,
        volunteer_id: int,
        limit: int = 100,
    ) -> list[VolunteerCourseCompletionItem]:
        started_at = perf_counter()
        cached = self._cache_get(volunteer_id, "course_completions")
        if cached is not None:
            return cached
        try:
            rows = await self.fetch_volunteer_course_completion_rows(
                volunteer_id, limit=limit
            )
            items = [VolunteerCourseCompletionItem.from_row(row) for row in rows]
            self._cache_set(volunteer_id, "course_completions", items)
            return items
        finally:
            log_operation_timing(
                logger,
                operation="volunteers.detail.course_completions",
                started_at=started_at,
                details={"volunteer_id": volunteer_id},
            )

    async def get_volunteer_relations(self, volunteer_id: int) -> VolunteerRelations:
        started_at = perf_counter()
        cached = self._cache_get(volunteer_id, "relations")
        if cached is not None:
            return cached
        try:
            rows = await self.fetch_volunteer_relation_rows(volunteer_id)
            relations = VolunteerRelations.from_rows(rows)
            self._cache_set(volunteer_id, "relations", relations)
            return relations
        finally:
            log_operation_timing(
                logger,
                operation="volunteers.detail.relations",
                started_at=started_at,
                details={"volunteer_id": volunteer_id},
            )

    # ── Option lists and lookups ───────────────────────────────────

    async def list_assignment_groups(self) -> list[GroupOption]:
        stmt = select(groups.c.id, groups.c.name, groups.c.is_active).order_by(
            groups.c.is_active.desc(), groups.c.name.asc(), groups.c.id.asc()
        )
        rows = await self.fetch_all_mappings(stmt)
        return [GroupOption.from_row(row) for row in rows]

    async def list_assignment_roles(self, group_id: int) -> list[AssignmentRoleOption]:
        stmt = (
            select(
                assignment_roles.c.id,
                assignment_roles.c.group_id,
                assignment_roles.c.name,
                assignment_roles.c.penguin_points,
            )
            .where(assignment_roles.c.group_id == group_id)
            .order_by(
                assignment_roles.c.name.asc().nullslast(), assignment_roles.c.id.asc()
            )
        )
        rows = await self.fetch_all_mappings(stmt)
        return [AssignmentRoleOption.from_row(row) for row in rows]

    async def find_volunteer_id_by_email(self, email: str) -> int | None:
        normalized = email.strip().lower()
        if not normalized:
            return None
        return await self.fetch_scalar(
            select(volunteer_records.c.id)
            .where(
                func.lower(func.coalesce(volunteer_records.c.email, ""))
                == normalized
            )
            .limit(1)
        )

    # ── Cache ──────────────────────────────────────────────────────

    def invalidate_volunteer_cache(self, volunteer_id: int) -> None:
        self._cache.pop(volunteer_id)

    def _cache_get(self, volunteer_id: int, key: str):
        namespace = self._cache.get(volunteer_id)
        return namespace.get(key) if namespace is not None else None

    def _cache_set(self, volunteer_id: int, key: str, value) -> None:
        namespace = dict(self._cache.get(volunteer_id) or {})
        namespace[key] = value
        self._cache.set(volunteer_id, namespace)

    # ── Row fetchers (one statement each; tests fake these) ───────

    async def list_volunteer_page_rows(
        self,
        *,
        limit: int,
        after_last_name: str | None = None,
        after_first_name: str | None = None,
        after_volunteer_id: int | None = None,
        only_active: bool = False,
    ) -> list[dict[str, Any]]:
        name_sort = name_sort_columns()
        active_volunteers = (
            current_active_volunteers_subquery() if only_active else None
        )
        stmt = (
            volunteer_list_base_stmt(active_volunteers=active_volunteers)
            .order_by(
                name_sort.last_name.asc(),
                name_sort.first_name.asc(),
                volunteer_records.c.id.asc(),
            )
            .limit(limit)
        )
        if (
            after_volunteer_id is not None
            and after_last_name is not None
            and after_first_name is not None
        ):
            stmt = stmt.where(
                or_(
                    name_sort.last_name > after_last_name,
                    and_(
                        name_sort.last_name == after_last_name,
                        name_sort.first_name > after_first_name,
                    ),
                    and_(
                        name_sort.last_name == after_last_name,
                        name_sort.first_name == after_first_name,
                        volunteer_records.c.id > after_volunteer_id,
                    ),
                )
            )
        return await self.fetch_all_mappings(stmt)

    async def search_volunteers_page(
        self,
        *,
        normalized_query: str,
        limit: int,
        offset: int = 0,
        only_active: bool = False,
    ) -> list[dict[str, Any]]:
        return await self.fetch_all_mappings(
            build_volunteer_search_stmt(
                normalized_query=normalized_query,
                limit=limit,
                offset=offset,
                only_active=only_active,
            )
        )

    async def fetch_volunteer_shell_row(
        self, volunteer_id: int
    ) -> dict[str, Any] | None:
        points = pingvin_points_subquery()
        discount_levels = current_discount_level_subquery()
        active_volunteers = current_active_volunteers_subquery()
        first_choice_group = groups.alias("first_choice_group")
        second_choice_group = groups.alias("second_choice_group")
        stmt = (
            select(
                volunteer_records.c.id,
                volunteer_records.c.first_name,
                volunteer_records.c.last_name,
                volunteer_records.c.email,
                volunteer_records.c.phone,
                volunteer_records.c.birth_date,
                volunteer_records.c.created_at,
                volunteer_records.c.gender,
                volunteer_records.c.street_address,
                volunteer_records.c.postal_code,
                func.coalesce(points.c.pingvin_points, 0).label("pingvin_points"),
                discount_levels.c.current_discount_level,
                active_volunteers.c.volunteer_id.is_not(None).label("is_active"),
                volunteer_photos.c.sha1,
                volunteer_photos.c.filetype,
                volunteer_application_invites.c.id.label("registration_id"),
                volunteer_application_invites.c.created_at.label("registration_created_at"),
                volunteer_application_invites.c.source.label("registration_source"),
                volunteer_application_invites.c.status.label("registration_status"),
                func.coalesce(
                    volunteer_application_invites.c.first_choice_label,
                    first_choice_group.c.name,
                ).label("first_choice_group_name"),
                func.coalesce(
                    volunteer_application_invites.c.second_choice_label,
                    second_choice_group.c.name,
                ).label("second_choice_group_name"),
                volunteer_application_group_members.c.group_id.label("registration_group_id"),
                volunteer_application_group_members.c.role.label("registration_group_role"),
                volunteer_application_group_members.c.status.label("registration_group_status"),
            )
            .select_from(
                volunteer_records.outerjoin(
                    volunteer_photos,
                    volunteer_photos.c.volunteer_id == volunteer_records.c.id,
                )
                .outerjoin(
                    points,
                    points.c.volunteer_id == volunteer_records.c.id,
                )
                .outerjoin(
                    discount_levels,
                    discount_levels.c.volunteer_id == volunteer_records.c.id,
                )
                .outerjoin(
                    active_volunteers,
                    active_volunteers.c.volunteer_id == volunteer_records.c.id,
                )
                .outerjoin(
                    volunteer_application_invites,
                    volunteer_application_invites.c.promoted_volunteer_id == volunteer_records.c.id,
                )
                .outerjoin(
                    first_choice_group,
                    first_choice_group.c.id == volunteer_application_invites.c.first_choice_group_id,
                )
                .outerjoin(
                    second_choice_group,
                    second_choice_group.c.id == volunteer_application_invites.c.second_choice_group_id,
                )
                .outerjoin(
                    volunteer_application_group_members,
                    volunteer_application_group_members.c.invite_id == volunteer_application_invites.c.id,
                )
            )
            .where(volunteer_records.c.id == volunteer_id)
            .limit(1)
        )
        return await self.fetch_first_mapping(stmt)

    async def fetch_volunteer_role_assignment_rows(
        self,
        volunteer_id: int,
        *,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(
                role_assignments.c.id,
                role_assignments.c.group_id,
                role_assignments.c.role_id,
                role_assignments.c.semester,
                role_assignments.c.contract_signed,
                groups.c.name.label("group_name"),
                assignment_roles.c.name.label("role_name"),
                assignment_roles.c.penguin_points,
            )
            .select_from(
                role_assignments.join(
                    groups, groups.c.id == role_assignments.c.group_id
                ).outerjoin(
                    assignment_roles,
                    assignment_roles.c.id == role_assignments.c.role_id,
                )
            )
            .where(role_assignments.c.volunteer_id == volunteer_id)
            .order_by(role_assignments.c.semester.desc(), role_assignments.c.id.desc())
            .limit(limit)
        )
        return await self.fetch_all_mappings(stmt)

    async def fetch_volunteer_course_completion_rows(
        self,
        volunteer_id: int,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(
                course_completions.c.id,
                course_completions.c.course_id,
                course_completions.c.completed_semester,
                courses.c.name.label("course_name"),
            )
            .select_from(
                course_completions.join(
                    courses, courses.c.id == course_completions.c.course_id
                )
            )
            .where(course_completions.c.volunteer_id == volunteer_id)
            .order_by(
                course_completions.c.completed_semester.desc(),
                course_completions.c.id.desc(),
            )
            .limit(limit)
        )
        return await self.fetch_all_mappings(stmt)

    async def fetch_volunteer_relation_rows(
        self, volunteer_id: int
    ) -> list[dict[str, Any]]:
        kin_stmt = select(
            literal("kin").label("relation_type"),
            volunteer_next_of_kin.c.id.label("relation_id"),
            volunteer_next_of_kin.c.name.label("primary_text"),
            volunteer_next_of_kin.c.phone.label("secondary_text"),
            volunteer_next_of_kin.c.created_at.label("created_at"),
        ).where(volunteer_next_of_kin.c.volunteer_id == volunteer_id)
        card_stmt = select(
            literal("card").label("relation_type"),
            volunteer_cards.c.id.label("relation_id"),
            volunteer_cards.c.card_number.label("primary_text"),
            literal(None, type_=Text()).label("secondary_text"),
            volunteer_cards.c.created_at.label("created_at"),
        ).where(volunteer_cards.c.volunteer_id == volunteer_id)
        relations = union_all(kin_stmt, card_stmt).subquery()
        stmt = select(
            relations.c.relation_type,
            relations.c.relation_id,
            relations.c.primary_text,
            relations.c.secondary_text,
            relations.c.created_at,
        ).order_by(relations.c.created_at.desc(), relations.c.relation_id.desc())
        return await self.fetch_all_mappings(stmt)


# ── Shared helpers ─────────────────────────────────────────────────


def require_media_token_service(
    media_token_service: MediaTokenService | None,
) -> MediaTokenService:
    if media_token_service is None:
        raise RuntimeError(
            "A media token service must be configured before building media URLs."
        )
    return media_token_service


def build_photo_url(
    media_token_service: MediaTokenService | None,
    sha1: str | None,
    filetype: str | None,
) -> str | None:
    if not sha1 or not filetype:
        return None
    return require_media_token_service(media_token_service).build_photo_media_url(
        f"{sha1}.{filetype}"
    )


def _encode_browse_cursor(row: dict[str, Any]) -> str:
    return _encode_cursor(
        {
            "mode": "browse",
            "last_name": row["last_name"],
            "first_name": row.get("first_name") or "",
            "volunteer_id": row["id"],
        }
    )


def _encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str | None) -> dict[str, Any]:
    if not cursor:
        return {}
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}
