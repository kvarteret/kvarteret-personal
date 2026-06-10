"""SMS gateway protocol.

Defines the port for sending SMS messages (e.g. OTP codes for
volunteer login).  No implementation is shipped — the email-code
flow remains the credential until a provider is chosen.

Provider selection (Twilio/Vonage vs. Norwegian aggregator such as
LinkMobility or Sveve) is an open decision to be recorded when SMS
is adopted.

See ``docs/adr/002-auth-consolidation.md``.
"""

from __future__ import annotations

from typing import Protocol


class SmsGateway(Protocol):
    async def send(self, *, phone_number: str, message: str) -> None: ...
