from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from secrets import choice

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, ConfigDict

from app.cache import TTLCache
from app.config import Settings
from app.media_tokens import MediaTokenService
from app.services.email import EmailSenderProtocol
from app.services.mobile_card_repository import MobileCardRepository, MobileCardSnapshot
from app.services.semester import get_current_semester_code

logger = logging.getLogger(__name__)


class MobileCardError(RuntimeError):
    pass


class MobileCardDuplicatePersonError(MobileCardError):
    pass


class MobileCardPersonNotFoundError(MobileCardError):
    pass


class MobileCardInvalidAccessCodeError(MobileCardError):
    pass


class MobileCardRateLimitedError(MobileCardError):
    pass


class MobileCardRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    group: str
    discount_level: int | None = None
    pingvin_points: int = 0
    signed_contract: bool = False


class MobileCardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_id: int
    first_name: str
    last_name: str
    birth_date: date | None = None
    created_at: datetime
    valid_until: datetime
    photo_url: str | None = None
    pingvin_points: int
    active_roles: list[MobileCardRole]
    word_of_the_day: str

    def to_legacy_dict(self) -> dict:
        return {
            "id": self.person_id,
            "fornavn": self.first_name,
            "etternavn": self.last_name,
            "fodselsdato": self.birth_date.isoformat() if self.birth_date else None,
            "opprettet": self.created_at.isoformat(),
            "gyldigTil": self.valid_until.isoformat(),
            "bildeUrl": self.photo_url,
            "pingvinPoengSum": self.pingvin_points,
            "aktiveVerv": [
                {
                    "navn": role.name,
                    "gruppe": role.group,
                    "rabattTrinn": role.discount_level,
                    "pingvinPoeng": role.pingvin_points,
                    "signertKontrakt": role.signed_contract,
                }
                for role in self.active_roles
            ],
            "dagensOrd": self.word_of_the_day,
        }


@dataclass(slots=True)
class MobileCardSession:
    session_token: str
    card: MobileCardResponse


class MobileCardService:
    def __init__(
        self,
        settings: Settings,
        repository: MobileCardRepository,
        email_sender: EmailSenderProtocol,
        media_token_service: MediaTokenService | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.email_sender = email_sender
        self.media_token_service = media_token_service
        self.serializer = URLSafeTimedSerializer(settings.app_secret_key, salt="kvarteret-mobile-card")
        self._access_code_request_counts: TTLCache[str, int] = TTLCache(
            ttl_seconds=settings.mobile_card_access_code_request_window_seconds,
            max_entries=4096,
        )
        self._session_attempt_counts: TTLCache[str, int] = TTLCache(
            ttl_seconds=settings.mobile_card_session_attempt_window_seconds,
            max_entries=4096,
        )

    async def request_access_code(self, email: str, *, source_key: str | None = None) -> None:
        normalized_email = email.strip().lower()
        if self._is_review_request(normalized_email, None):
            return None
        request_keys = _build_rate_limit_keys(normalized_email, source_key)
        self._enforce_rate_limit(
            cache=self._access_code_request_counts,
            keys=request_keys,
            limit=self.settings.mobile_card_access_code_request_limit,
            message="Too many access-code requests. Try again later.",
        )
        self._increment_rate_limit(self._access_code_request_counts, request_keys)

        volunteers = await self.repository.find_volunteers_by_email(normalized_email)
        if len(volunteers) > 1:
            raise MobileCardDuplicatePersonError(
                "More than one person uses this email address. Contact an administrator."
            )
        if not volunteers:
            raise MobileCardPersonNotFoundError(
                "Email not found in the personnel database."
            )

        volunteer_row = volunteers[0]
        now = datetime.now(UTC)
        existing_created_at = volunteer_row["internkort_access_token_created_at"]
        existing_access_code = volunteer_row["internkortaccesstoken"]
        if (
            existing_access_code
            and existing_created_at
            and now - existing_created_at <= timedelta(seconds=self.settings.mobile_card_access_code_cooldown_seconds)
        ):
            access_code = str(existing_access_code)
            logger.info("Reused recent mobile-card access code for volunteer %s", volunteer_row["id"])
        else:
            access_code = _generate_access_code()
            await self.repository.store_access_code(
                volunteer_id=volunteer_row["id"],
                access_code=access_code,
                created_at=now,
            )
            logger.info("Generated mobile-card access code for volunteer %s", volunteer_row["id"])

        await self.email_sender.send_email(
            recipient_email=email.strip(),
            subject="Kvarteret Internkort is ready for you",
            html_body=_build_access_code_email_body(
                access_code=access_code,
                expires_in_minutes=self.settings.mobile_card_access_code_ttl_minutes,
            ),
        )
        logger.info("Sent mobile-card access code email for volunteer %s", volunteer_row["id"])
        return None

    async def create_session(self, email: str, access_code: str, *, source_key: str | None = None) -> MobileCardSession:
        normalized_email = email.strip().lower()
        normalized_access_code = access_code.strip()
        if self._is_review_request(normalized_email, normalized_access_code):
            card = self._build_review_card()
            token = self.serializer.dumps({"person_id": 0, "review": True})
            return MobileCardSession(session_token=token, card=card)
        attempt_keys = _build_rate_limit_keys(normalized_email, source_key)
        self._enforce_rate_limit(
            cache=self._session_attempt_counts,
            keys=attempt_keys,
            limit=self.settings.mobile_card_session_attempt_limit,
            message="Too many access-code attempts. Try again later.",
        )

        volunteer_row = await self.repository.find_volunteer_by_email_and_code(
            email=normalized_email,
            access_code=normalized_access_code,
            expires_after=datetime.now(UTC) - timedelta(minutes=self.settings.mobile_card_access_code_ttl_minutes),
        )
        if volunteer_row is None:
            self._increment_rate_limit(self._session_attempt_counts, attempt_keys)
            raise MobileCardInvalidAccessCodeError("Invalid access code.")
        self._clear_rate_limit(self._session_attempt_counts, attempt_keys)
        token = self.serializer.dumps({"person_id": volunteer_row["id"]})
        card = await self._build_card(volunteer_row["id"])
        return MobileCardSession(session_token=token, card=card)

    async def get_current_card(self, session_token: str) -> MobileCardResponse:
        try:
            payload = self.serializer.loads(
                session_token,
                max_age=self.settings.mobile_card_session_ttl_days * 24 * 3600,
            )
        except (BadSignature, SignatureExpired) as exc:
            raise MobileCardInvalidAccessCodeError("Unknown session token.") from exc

        if payload.get("review") is True:
            return self._build_review_card()
        person_id = payload.get("person_id")
        if not isinstance(person_id, int):
            raise MobileCardInvalidAccessCodeError("Unknown session token.")
        return await self._build_card(person_id)

    async def _build_card(self, volunteer_id: int) -> MobileCardResponse:
        current_semester = get_current_semester_code()
        snapshot = await self.repository.fetch_card_snapshot(volunteer_id=volunteer_id, semester_code=current_semester)
        if snapshot is None:
            raise MobileCardPersonNotFoundError(f"Volunteer {volunteer_id} was not found.")
        return self._build_card_response(snapshot)

    def _build_card_response(self, snapshot: MobileCardSnapshot) -> MobileCardResponse:
        photo_url = (
            self.media_token_service.build_photo_media_url(snapshot.photo_path)
            if snapshot.photo_path and self.media_token_service is not None
            else None
        )
        return MobileCardResponse(
            person_id=snapshot.volunteer_id,
            first_name=snapshot.first_name,
            last_name=snapshot.last_name,
            birth_date=snapshot.birth_date,
            created_at=snapshot.created_at,
            valid_until=datetime.now(UTC) + timedelta(days=self.settings.mobile_card_session_ttl_days),
            photo_url=photo_url,
            pingvin_points=snapshot.pingvin_points,
            active_roles=[
                MobileCardRole(
                    name=role.name,
                    group=role.group,
                    discount_level=role.discount_level,
                    pingvin_points=role.pingvin_points,
                    signed_contract=role.signed_contract,
                )
                for role in snapshot.active_roles
            ],
            word_of_the_day=_word_of_the_day(),
        )

    def _is_review_request(self, email: str, access_code: str | None) -> bool:
        if not self.settings.review_bypass_enabled:
            return False
        if not self.settings.review_bypass_email or not self.settings.review_bypass_token:
            return False
        return email == self.settings.review_bypass_email.lower() and (
            access_code is None or access_code == self.settings.review_bypass_token
        )

    def _build_review_card(self) -> MobileCardResponse:
        return MobileCardResponse(
            person_id=0,
            first_name="Review",
            last_name="User",
            birth_date=date(1990, 1, 1),
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            valid_until=datetime.now(UTC) + timedelta(days=365),
            photo_url=None,
            pingvin_points=42,
            active_roles=[
                MobileCardRole(
                    name="Guest",
                    group="Kvarteret",
                    discount_level=0,
                    pingvin_points=0,
                    signed_contract=True,
                )
            ],
            word_of_the_day=_word_of_the_day(),
        )

    def _enforce_rate_limit(self, *, cache: TTLCache[str, int], keys: tuple[str, ...], limit: int, message: str) -> None:
        if limit < 1:
            return
        if any((cache.get(key) or 0) >= limit for key in keys):
            raise MobileCardRateLimitedError(message)

    def _increment_rate_limit(self, cache: TTLCache[str, int], keys: tuple[str, ...]) -> None:
        for key in keys:
            cache.set(key, (cache.get(key) or 0) + 1)

    def _clear_rate_limit(self, cache: TTLCache[str, int], keys: tuple[str, ...]) -> None:
        for key in keys:
            cache.pop(key)


def _generate_access_code(length: int = 6) -> str:
    digits = "0123456789"
    return "".join(choice(digits) for _ in range(length))


def _build_access_code_email_body(*, access_code: str, expires_in_minutes: int) -> str:
    return (
        "Your Kvarteret verification code is:"
        "<br><br>"
        f"{access_code}"
        "<br><br>"
        f"This code expires in {expires_in_minutes} minutes."
        "<br><br>"
        "If you didn't request this code, you can ignore this email."
    )


def _build_rate_limit_keys(email: str, source_key: str | None) -> tuple[str, ...]:
    keys = [f"email:{email}"]
    if source_key:
        keys.append(f"source:{source_key}")
        keys.append(f"email-source:{email}:{source_key}")
    return tuple(keys)


def _word_of_the_day() -> str:
    words = [
        "pingvin",
        "vakt",
        "bar",
        "scene",
        "kaffe",
        "frivillig",
        "kvarter",
    ]
    return words[datetime.now(UTC).timetuple().tm_yday % len(words)]
