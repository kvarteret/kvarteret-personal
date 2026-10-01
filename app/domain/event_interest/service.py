from uuid import UUID

from app.domain.event_interest.repository import EventInterestRepository


class EventInterestService:
    def __init__(self, repository: EventInterestRepository) -> None:
        self.repository = repository

    async def read(self, event_id: str, source_hash: str | None) -> dict[str, int]:
        return await self.repository.read(event_id, source_hash)

    async def save(
        self, event_id: str, source_hash: str, clicks: int, batch_id: str
    ) -> dict[str, int]:
        if type(clicks) is not int or not 1 <= clicks <= 1000:
            raise ValueError("Clicks must be an integer between 1 and 1000 per batch")
        if str(UUID(batch_id)) != batch_id:
            raise ValueError("Invalid batch ID")
        return await self.repository.save(event_id, source_hash, clicks, batch_id)
