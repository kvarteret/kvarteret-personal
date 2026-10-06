from __future__ import annotations

from sqlalchemy import text

from app.db.repository import SqlAlchemyRepository


class EventInterestRepository(SqlAlchemyRepository):
    async def read(self, event_id: str, source_hash: str | None) -> dict[str, int]:
        row = await self.fetch_one_mapping(
            text("""
            SELECT COALESCE(SUM(clicks) FILTER (WHERE source_hash = :source), 0)::bigint AS taps,
              COALESCE(SUM(clicks), 0)::bigint AS count
            FROM public.event_interest_clicks
            WHERE event_id = :event AND expires_at > now()
            """).bindparams(event=event_id, source=source_hash)
        )
        return {"taps": row["taps"], "count": row["count"]}

    async def save(
        self, event_id: str, source_hash: str, clicks: int, batch_id: str
    ) -> dict[str, int]:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:event, 0))"),
            {"event": event_id},
        )
        await self.session.execute(
            text("""
                DELETE FROM public.event_interest_clicks
                WHERE event_id = :event AND expires_at <= now()
            """),
            {"event": event_id},
        )
        # The lock also makes the full-heart limit atomic across tabs sharing a
        # cookie. Retrying an earlier batch remains a no-op below.
        current = await self.read(event_id, source_hash)
        accepted = min(clicks, max(0, 12 - current["taps"]))
        if accepted == 0:
            return current
        await self.session.execute(
            text("""
                INSERT INTO public.event_interest_clicks
                    (event_id, source_hash, batch_id, clicks)
                VALUES (:event, :source, CAST(:batch AS uuid), :clicks)
                ON CONFLICT (event_id, batch_id) DO NOTHING
            """),
            {
                "event": event_id,
                "source": source_hash,
                "batch": batch_id,
                "clicks": accepted,
            },
        )
        return await self.read(event_id, source_hash)
