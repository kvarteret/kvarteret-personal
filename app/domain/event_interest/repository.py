from __future__ import annotations

from sqlalchemy import text

from app.db.repository import SqlAlchemyRepository


class EventInterestRepository(SqlAlchemyRepository):
    async def read(
        self, event_id: str, source_hash: str | None
    ) -> dict[str, float | int]:
        row = await self.fetch_one_mapping(
            text("""
            SELECT COALESCE(MAX(taps) FILTER (WHERE source_hash = :source), 0)::int AS taps,
              COALESCE(SUM(CASE WHEN taps >= 8 THEN 1 WHEN taps >= 4 THEN 0.75 ELSE 0.25 END), 0)::float8 AS score
            FROM public.event_interest WHERE event_id = :event AND expires_at > now()
        """).bindparams(event=event_id, source=source_hash)
        )
        return {"taps": row["taps"], "score": row["score"]}

    async def save(
        self, event_id: str, source_hash: str, taps: int
    ) -> dict[str, float | int]:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:event, 0))"),
            {"event": event_id},
        )
        # Prune only this event's expired rows using the primary-key prefix.
        # A daily cleanup job removes all other expired records.
        await self.session.execute(
            text(
                "DELETE FROM public.event_interest WHERE event_id = :event AND expires_at <= now()"
            ),
            {"event": event_id},
        )
        if taps == 0:
            await self.session.execute(
                text(
                    "DELETE FROM public.event_interest WHERE event_id = :event AND source_hash = :source"
                ),
                {"event": event_id, "source": source_hash},
            )
        else:
            await self.session.execute(
                text("""
                INSERT INTO public.event_interest (event_id, source_hash, taps)
                VALUES (:event, :source, :taps)
                ON CONFLICT (event_id, source_hash) DO UPDATE
                SET taps = GREATEST(event_interest.taps, EXCLUDED.taps)
            """),
                {"event": event_id, "source": source_hash, "taps": taps},
            )
        return await self.read(event_id, source_hash)
