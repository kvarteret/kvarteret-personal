from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repository import SqlAlchemyRepository
from app.db.tables import (
    event_organizer_group_memberships,
    event_organizer_groups,
    event_types,
    events,
    rooms,
)


class EventsRepository(SqlAlchemyRepository):
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None = None
    ) -> None:
        super().__init__(session_factory=session_factory)

    async def list_events(
        self,
        *,
        include_internal: bool,
        now: datetime,
        fetch_limit: int,
    ) -> list[dict[str, Any]]:
        stmt = (
            _event_select()
            .where(events.c.status == "published")
            .where(events.c.event_start.is_not(None))
            .where(events.c.event_end.is_not(None))
            .where(events.c.event_end >= now)
            .order_by(events.c.event_start.asc())
            .limit(fetch_limit)
        )
        if not include_internal:
            stmt = stmt.where(events.c.is_internal.is_(False))
        rows = await self.fetch_all_mappings(stmt)
        return await self._attach_organizer_groups(rows)

    async def get_event(self, event_id: UUID) -> dict[str, Any] | None:
        row = await self.fetch_first_mapping(
            _event_select().where(events.c.id == event_id)
        )
        if row is None:
            return None
        return (await self._attach_organizer_groups([row]))[0]

    async def list_event_types(self) -> list[dict[str, Any]]:
        stmt = (
            select(
                event_types.c.id,
                event_types.c.slug,
                event_types.c.name,
                event_types.c.description,
                event_types.c.taxonomy_group,
                event_types.c.sort_order,
                event_types.c.is_active,
            )
            .where(event_types.c.is_active.is_(True))
            .order_by(event_types.c.sort_order.asc(), event_types.c.name.asc())
        )
        return await self.fetch_all_mappings(stmt)

    async def list_organizer_groups(self) -> list[dict[str, Any]]:
        stmt = (
            select(
                event_organizer_groups.c.id,
                event_organizer_groups.c.slug,
                event_organizer_groups.c.name,
                event_organizer_groups.c.sort_order,
                event_organizer_groups.c.is_active,
                event_organizer_groups.c.default_event_type_id,
            )
            .where(event_organizer_groups.c.is_active.is_(True))
            .order_by(
                event_organizer_groups.c.sort_order.asc(),
                event_organizer_groups.c.name.asc(),
            )
        )
        return await self.fetch_all_mappings(stmt)

    async def list_rooms(self) -> list[dict[str, Any]]:
        stmt = (
            select(
                rooms.c.id,
                rooms.c.slug,
                rooms.c.name,
                rooms.c.sort_order,
                rooms.c.is_active,
            )
            .where(rooms.c.is_active.is_(True))
            .order_by(rooms.c.sort_order.asc(), rooms.c.name.asc())
        )
        return await self.fetch_all_mappings(stmt)

    async def _attach_organizer_groups(
        self,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        event_ids = [row["id"] for row in rows]
        if not event_ids:
            return rows

        stmt = (
            select(
                event_organizer_group_memberships.c.event_id,
                event_organizer_group_memberships.c.display_order,
                event_organizer_groups.c.id,
                event_organizer_groups.c.slug,
                event_organizer_groups.c.name,
                event_organizer_groups.c.sort_order,
                event_organizer_groups.c.is_active,
                event_organizer_groups.c.default_event_type_id,
            )
            .select_from(
                event_organizer_group_memberships.join(
                    event_organizer_groups,
                    event_organizer_groups.c.id
                    == event_organizer_group_memberships.c.organizer_group_id,
                )
            )
            .where(event_organizer_group_memberships.c.event_id.in_(event_ids))
            .order_by(
                event_organizer_group_memberships.c.event_id.asc(),
                event_organizer_group_memberships.c.display_order.asc(),
            )
        )
        memberships = await self.fetch_all_mappings(stmt)
        organizer_groups_by_event_id: dict[Any, list[dict[str, Any]]] = {
            event_id: [] for event_id in event_ids
        }
        for membership in memberships:
            organizer_groups_by_event_id[membership["event_id"]].append(
                {
                    "id": membership["id"],
                    "slug": membership["slug"],
                    "name": membership["name"],
                    "sort_order": membership["sort_order"],
                    "is_active": membership["is_active"],
                    "default_event_type_id": membership["default_event_type_id"],
                }
            )
        for row in rows:
            row["organizer_groups"] = organizer_groups_by_event_id[row["id"]]
        return rows


def _event_select():
    """Factory: creates a fresh select each call so callers can mutate safely."""
    return select(
        events.c.id,
        events.c.slug,
        events.c.status,
        events.c.event_start,
        events.c.event_end,
        events.c.created_at,
        events.c.updated_at,
        events.c.ticket_url,
        events.c.facebook_url,
        events.c.image_url,
        events.c.price,
        events.c.event_type_id,
        events.c.room_id,
        events.c.room_text,
        events.c.is_internal,
        events.c.is_featured,
        events.c.recurring_interval_days,
        events.c.translations,
        event_types.c.id.label("event_type__id"),
        event_types.c.slug.label("event_type__slug"),
        event_types.c.name.label("event_type__name"),
        event_types.c.description.label("event_type__description"),
        event_types.c.taxonomy_group.label("event_type__taxonomy_group"),
        event_types.c.sort_order.label("event_type__sort_order"),
        event_types.c.is_active.label("event_type__is_active"),
        rooms.c.id.label("room__id"),
        rooms.c.slug.label("room__slug"),
        rooms.c.name.label("room__name"),
        rooms.c.sort_order.label("room__sort_order"),
        rooms.c.is_active.label("room__is_active"),
    ).select_from(
        events.join(event_types, event_types.c.id == events.c.event_type_id).outerjoin(
            rooms,
            rooms.c.id == events.c.room_id,
        )
    )
