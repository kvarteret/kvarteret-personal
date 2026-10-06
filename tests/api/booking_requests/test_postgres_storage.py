"""Concurrency regression; runs in the existing Postgres migrations CI job."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.config import Settings
from app.db.session import build_database_runtime, session_scope
from app.domain.booking_requests.models import BookingSnapshot
from app.domain.booking_requests.repository import BookingRequestsRepository
from app.domain.booking_requests.service import BookingRequestsService


@pytest.mark.asyncio
async def test_concurrent_retries_preserve_one_snapshot():
    url = os.environ.get("E2E_DATABASE_URL", "")
    if not url.startswith("postgresql+asyncpg"):
        pytest.skip("requires migrated Postgres")
    runtime = build_database_runtime(Settings(app_env="test", database_url=url))
    submission_id = uuid4()
    snapshot = BookingSnapshot(
        schema_version=1,
        submission_id=submission_id,
        kind="room",
        event_name="Test",
        contact_name="Test",
        contact_email="test@example.com",
        room_ids=[97],
        schedule=[
            {"date": "2026-10-15", "doors_open": "20:00", "doors_close": "02:00"}
        ],
        form={},
        crescat_payload={},
    )

    async def store():
        async with session_scope(runtime):
            return await BookingRequestsService(BookingRequestsRepository()).store(
                snapshot
            )

    try:
        receipts = await asyncio.gather(*(store() for _ in range(8)))
        assert len({r.booking_request_id for r in receipts}) == 1
        snapshot.event_name = "Edited"
        await store()
        async with session_scope(runtime) as session:
            count = await session.scalar(
                text(
                    "SELECT count(*) FROM public.booking_requests WHERE submission_id=:id"
                ),
                {"id": submission_id},
            )
            assert count == 2
    finally:
        async with session_scope(runtime) as session:
            await session.execute(
                text("DELETE FROM public.booking_requests WHERE submission_id=:id"),
                {"id": submission_id},
            )
        await runtime.aclose()
