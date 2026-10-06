"""Async Resend HTTPS transport; template rendering remains in the application."""

from __future__ import annotations

from uuid import uuid4

import httpx

from app.config import Settings
from app.errors import NotConfiguredError
from app.infrastructure.email.protocols import EmailDeliveryError


class ResendDeliveryError(EmailDeliveryError):
    """Value-free provider diagnostics safe for logs and admin recovery."""

    def __init__(
        self,
        category: str,
        *,
        retryable: bool,
        http_status: int | None = None,
        delivery_uncertain: bool = False,
    ) -> None:
        super().__init__(category)
        self.category = category
        self.retryable = retryable
        self.http_status = http_status
        self.delivery_uncertain = delivery_uncertain
        self.phase = "resend"


class ResendEmailSender:
    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.settings = settings
        self.transport = transport

    async def send_email(
        self,
        *,
        recipient_email: str,
        subject: str,
        html_body: str,
        idempotency_key: str | None = None,
    ) -> None:
        if not self.settings.resend_api_key:
            raise NotConfiguredError("Resend email is not configured.")
        headers = {
            "Authorization": f"Bearer {self.settings.resend_api_key}",
            "Idempotency-Key": idempotency_key or f"email/{uuid4()}",
        }
        try:
            async with httpx.AsyncClient(
                timeout=15, transport=self.transport
            ) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers=headers,
                    json={
                        "from": f"{self.settings.email_sender_name} <{self.settings.email_sender_email}>",
                        "to": [recipient_email],
                        "subject": subject,
                        "html": html_body,
                    },
                )
        except httpx.TransportError:
            # The provider may have accepted a timed-out request. The queue
            # retries with the same key inside Resend's 24-hour window.
            raise ResendDeliveryError(
                "resend_connection",
                retryable=True,
                delivery_uncertain=True,
            ) from None
        if response.is_success:
            try:
                accepted = response.json()
                if (
                    not isinstance(accepted, dict)
                    or not isinstance(accepted.get("id"), str)
                    or not accepted["id"]
                ):
                    raise ValueError
            except (ValueError, TypeError):
                raise ResendDeliveryError(
                    "resend_invalid_response",
                    retryable=True,
                    delivery_uncertain=True,
                ) from None
            return
        retryable = response.status_code == 429 or response.status_code >= 500
        # A concurrent retry with the same key can return 409; a mismatching
        # payload is permanent and must not be retried with a different key.
        if response.status_code == 409:
            try:
                retryable = (
                    response.json().get("name") == "concurrent_idempotent_requests"
                )
            except (ValueError, AttributeError):
                pass
        raise ResendDeliveryError(
            "resend_temporary" if retryable else "resend_permanent",
            retryable=retryable,
            http_status=response.status_code,
        ) from None
