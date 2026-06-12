from __future__ import annotations

from typing import Protocol


class EmailDeliveryError(RuntimeError):
    """Raised by any sender when an email cannot be delivered."""


class EmailSenderProtocol(Protocol):
    async def send_email(
        self, *, recipient_email: str, subject: str, html_body: str
    ) -> None: ...
