from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.repository import SqlAlchemyRepository
from app.domain.booking_requests.tables import booking_requests


class BookingRequestsRepository(SqlAlchemyRepository):
    async def store(
        self, submission_id: UUID, content_hash: str, snapshot: dict
    ) -> UUID:
        # A no-op conflict update waits for an in-flight winner and returns its
        # receipt in the same statement. No snapshot or timestamp is overwritten.
        statement = (
            insert(booking_requests)
            .values(
                id=uuid4(),
                submission_id=submission_id,
                content_hash=content_hash,
                snapshot=snapshot,
            )
            .on_conflict_do_update(
                constraint="booking_requests_submission_content_key",
                set_={"content_hash": content_hash},
            )
            .returning(booking_requests.c.id)
        )
        return await self.fetch_scalar(statement)

    async def get_snapshot(self, receipt_id: UUID, submission_id: UUID) -> dict | None:
        return await self.fetch_scalar(
            select(booking_requests.c.snapshot).where(
                booking_requests.c.id == receipt_id,
                booking_requests.c.submission_id == submission_id,
            )
        )
