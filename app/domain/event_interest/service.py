from app.domain.event_interest.repository import EventInterestRepository


class EventInterestService:
    def __init__(self, repository: EventInterestRepository) -> None:
        self.repository = repository

    async def read(
        self, event_id: str, source_hash: str | None
    ) -> dict[str, float | int]:
        return await self.repository.read(event_id, source_hash)

    async def save(
        self, event_id: str, source_hash: str, taps: int
    ) -> dict[str, float | int]:
        if type(taps) is not int or not 0 <= taps <= 12:
            raise ValueError("Taps must be an integer between 0 and 12")
        return await self.repository.save(event_id, source_hash, taps)
