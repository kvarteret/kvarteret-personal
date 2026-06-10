from __future__ import annotations

from typing import Literal


class MobileCardError(RuntimeError):
    pass


class MobileCardDuplicatePersonError(MobileCardError):
    pass


class MobileCardPersonNotFoundError(MobileCardError):
    pass


class MobileCardInvalidAccessCodeError(MobileCardError):
    pass


class MobileCardInvalidSessionError(MobileCardInvalidAccessCodeError):
    def __init__(
        self, message: str, *, reason: Literal["bad_signature", "expired", "malformed"]
    ) -> None:
        super().__init__(message)
        self.reason = reason


class MobileCardRateLimitedError(MobileCardError):
    pass
