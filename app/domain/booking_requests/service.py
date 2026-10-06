import hashlib
import json

from app.domain.booking_requests.models import BookingReceipt, BookingSnapshot
from app.domain.booking_requests.repository import BookingRequestsRepository


class BookingRequestsService:
    def __init__(self, repository: BookingRequestsRepository):
        self.repository = repository

    async def store(self, snapshot: BookingSnapshot) -> BookingReceipt:
        data = snapshot.model_dump(mode="json")
        content_hash = hashlib.sha256(
            json.dumps(
                data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
        request_id = await self.repository.store(
            snapshot.submission_id, content_hash, data
        )
        return BookingReceipt(
            booking_request_id=request_id,
            submission_id=snapshot.submission_id,
            content_hash=content_hash,
        )
