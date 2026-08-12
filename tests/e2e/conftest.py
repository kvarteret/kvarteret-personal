"""Fixtures for end-to-end tests against a real migrated Postgres.

These tests need ``E2E_DATABASE_URL`` pointing at a Postgres database
that has been migrated to head (``alembic upgrade head``) with the
Supabase compatibility stubs from ``.github/workflows/ci.yml`` applied.
They exercise the real application stack — middleware, unit of work,
repositories, state machine, Postgres rate limiter — with only the
boundary adapters (SMTP, admin auth) faked.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

E2E_DATABASE_URL = os.environ.get("E2E_DATABASE_URL")

requires_e2e_database = pytest.mark.skipif(
    not E2E_DATABASE_URL,
    reason="E2E_DATABASE_URL not set (needs a migrated Postgres)",
)


@dataclass
class CapturedEmail:
    recipient_email: str
    subject: str
    html_body: str


@dataclass
class CapturingEmailSender:
    sent: list[CapturedEmail] = field(default_factory=list)

    async def send_email(
        self, *, recipient_email: str, subject: str, html_body: str
    ) -> None:
        self.sent.append(
            CapturedEmail(
                recipient_email=recipient_email,
                subject=subject,
                html_body=html_body,
            )
        )


@dataclass
class FakeStorageService:
    """In-memory stand-in for the Azure-backed StorageService.

    Exercises the real photo-upload code path (validation, processing,
    storage call, cleanup) without needing Azure credentials.
    """

    uploaded: dict[str, bytes] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)

    def upload_photo(
        self, path: str, content: bytes, content_type: str | None = None
    ) -> None:
        self.uploaded[path] = content

    def remove_photo(self, path: str) -> None:
        self.removed.append(path)
        self.uploaded.pop(path, None)

    def close(self) -> None:
        return None


def make_test_jpeg() -> bytes:
    """A small but real JPEG that passes ``process_uploaded_photo``."""
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (64, 64), (180, 40, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest_asyncio.fixture
async def e2e_engine():
    engine = create_async_engine(E2E_DATABASE_URL)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def clean_database(e2e_engine):
    """Truncate the lifecycle tables before each test."""
    tables = [
        "domain_events",
        "volunteer_application_friend_invitations",
        "volunteer_application_submissions",
        "volunteer_application_invites",
        "role_assignments",
        "course_completions",
        "volunteer_cards",
        "volunteer_next_of_kin",
        "volunteer_photos",
        "volunteer_records",
        "rate_limits",
        "groups",
    ]
    async with e2e_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE "
                + ", ".join(f"public.{name}" for name in tables)
                + " RESTART IDENTITY CASCADE"
            )
        )
    return None
