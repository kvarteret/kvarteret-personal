from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings
from app.domain.mobile_card.models import DecodedMobileCardSession
from app.domain.mobile_card.errors import MobileCardInvalidSessionError
from app.observability import get_domain_logger

_UNKNOWN_SESSION_TOKEN = "Unknown session token."
logger = get_domain_logger(__name__)


class MobileCardSessionManager:
    """Token signing, decoding, renewal, and expiration for mobile-card sessions."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.serializer = URLSafeTimedSerializer(
            settings.app_secret_key, salt="kvarteret-mobile-card"
        )

    def build_token(self, payload: dict[str, int | bool]) -> str:
        return self.serializer.dumps(payload)

    def decode_token(self, session_token: str) -> DecodedMobileCardSession:
        now = datetime.now(UTC)
        try:
            payload, issued_at = self.serializer.loads(
                session_token,
                max_age=self._ttl_seconds(),
                return_timestamp=True,
            )
        except SignatureExpired as exc:
            self._log_invalid("expired")
            raise MobileCardInvalidSessionError(
                _UNKNOWN_SESSION_TOKEN, reason="expired"
            ) from exc
        except BadSignature as exc:
            self._log_invalid("bad_signature")
            raise MobileCardInvalidSessionError(
                _UNKNOWN_SESSION_TOKEN, reason="bad_signature"
            ) from exc

        if not isinstance(payload, dict):
            self._log_invalid("malformed")
            raise MobileCardInvalidSessionError(
                _UNKNOWN_SESSION_TOKEN, reason="malformed"
            )

        is_review = payload.get("review") is True
        person_id = payload.get("person_id")
        trial_application_id = payload.get("trial_application_id")

        if (
            not is_review
            and not isinstance(person_id, int)
            and not isinstance(trial_application_id, int)
        ):
            self._log_invalid("malformed")
            raise MobileCardInvalidSessionError(
                _UNKNOWN_SESSION_TOKEN, reason="malformed"
            )

        age_seconds = max(0, int((now - issued_at).total_seconds()))
        remaining_seconds = max(0, self._ttl_seconds() - age_seconds)

        return DecodedMobileCardSession(
            age_seconds=age_seconds,
            is_review=is_review,
            person_id=person_id if isinstance(person_id, int) else None,
            trial_application_id=(
                trial_application_id if isinstance(trial_application_id, int) else None
            ),
            remaining_seconds=remaining_seconds,
        )

    def maybe_renew(self, decoded: DecodedMobileCardSession) -> str | None:
        if decoded.remaining_seconds > self._renewal_threshold_seconds():
            return None

        if decoded.is_review:
            payload = {"person_id": 0, "review": True}
        elif decoded.trial_application_id is not None:
            payload = {"trial_application_id": decoded.trial_application_id}
        else:
            payload = {"person_id": decoded.person_id or 0}
        renewed_token = self.build_token(payload)
        logger.event(
            "mobile_card.session.renewed",
            fields={
                "subject_type": (
                    "review"
                    if decoded.is_review
                    else "trial_application"
                    if decoded.trial_application_id is not None
                    else "volunteer"
                ),
                "subject_id": (
                    decoded.trial_application_id
                    if decoded.trial_application_id is not None
                    else decoded.person_id
                ),
                "duration_ms": decoded.age_seconds * 1000,
                "outcome": "success",
            },
        )
        return renewed_token

    def _ttl_seconds(self) -> int:
        return self.settings.mobile_card_session_ttl_days * 24 * 3600

    def _renewal_threshold_seconds(self) -> int:
        return self.settings.mobile_card_session_renewal_threshold_days * 24 * 3600

    def _log_invalid(
        self, reason: Literal["bad_signature", "expired", "malformed"]
    ) -> None:
        logger.event(
            "mobile_card.session.expired"
            if reason == "expired"
            else "mobile_card.session.invalid",
            fields={
                "reason_code": reason,
                "outcome": "failure",
            },
        )
