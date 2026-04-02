from __future__ import annotations

from typing import Protocol


class EmailSenderProtocol(Protocol):
    async def send_email(self, *, recipient_email: str, subject: str, html_body: str) -> None: ...
