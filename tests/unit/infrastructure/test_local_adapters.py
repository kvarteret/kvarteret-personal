from __future__ import annotations

import logging

import pytest

from app.errors import NotConfiguredError
from app.infrastructure.email.console import ConsoleEmailSender
from app.infrastructure.storage.local_dir import LocalDirectoryStorage


@pytest.mark.asyncio
async def test_console_email_sender_writes_html_and_logs_links(
    tmp_path, caplog
) -> None:
    sender = ConsoleEmailSender(tmp_path)

    with caplog.at_level(logging.INFO):
        await sender.send_email(
            recipient_email="applicant@example.com",
            subject="Complete your profile",
            html_body='<a href="http://localhost:8000/apply/token">Apply</a>',
        )

    messages = list(tmp_path.glob("*.html"))
    assert len(messages) == 1
    assert "Apply" in messages[0].read_text(encoding="utf-8")
    assert "applicant@example.com" in caplog.text
    assert "http://localhost:8000/apply/token" in caplog.text


def test_local_directory_storage_round_trip(tmp_path) -> None:
    storage = LocalDirectoryStorage(tmp_path)

    storage.upload_photo("photo.jpg", b"photo-bytes", "image/jpeg")

    assert storage.download_photo("photo.jpg") == b"photo-bytes"
    storage.remove_photo("photo.jpg")
    with pytest.raises(NotConfiguredError, match="not present locally"):
        storage.download_photo("photo.jpg")


@pytest.mark.parametrize("path", ["../photo.jpg", "/tmp/photo.jpg", "nested/photo.jpg"])
def test_local_directory_storage_rejects_path_traversal(tmp_path, path: str) -> None:
    storage = LocalDirectoryStorage(tmp_path)

    with pytest.raises(NotConfiguredError, match="Invalid photo path"):
        storage.upload_photo(path, b"photo-bytes")
