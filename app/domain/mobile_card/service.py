from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from secrets import choice
from typing import Literal

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, ConfigDict

from app.cache import TTLCache
from app.config import Settings
from app.infrastructure.email.mobile_card_templates import (
    MobileCardEmailTemplateRenderer,
    MobileCardEmailTemplateRendererProtocol,
)
from app.media_tokens import MediaTokenService
from app.infrastructure.email.protocols import EmailSenderProtocol
from app.infrastructure.email.smtp import SmtpDeliveryError
from app.domain.mobile_card.april_state import MobileCardAprilStateService
from app.domain.mobile_card.repository import MobileCardRepository, MobileCardSnapshot
from app.infrastructure.formatting.semester import get_current_semester_code

_UNKNOWN_SESSION_TOKEN = "Unknown session token."

logger = logging.getLogger(__name__)

_APRIL_FOOLS_IMAGE_BY_GROUP_ID = {
    2: "hovedstyret.avif",
    78: "vaktetaten.jpg",
    83: "asf-aktive-studenter--hits-for-kids.jpg",
    146: "kraftetaten.webp",
    195: "immaturus.avif",
    253: "skjenkeetaten.webp",
    254: "e-tjenesten.jpeg",
    260: "pingvinordenen.jpeg",
    264: "samfunnet-i-bergen.jpeg",
    265: "bergen-realistforening.jpg",
    266: "bergen-filmklubb.png",
    267: "immaturus.avif",
    268: "asf-aktive-studenter--hits-for-kids.jpg",
    270: "pr.jpg",
    271: "pr.jpg",
    272: "arme-riddere.jpg",
    277: "blak.jpg",
    278: "sirenene.jpg",
    284: "hf.jpg",
}
_APRIL_FOOLS_DEFAULT_IMAGE = "default.jpg"

_LEGACY_PENGUIN_WORD_PREFIXES = [
    "bug",
    "mordi",
    "adelie",
    "bøyle",
    "dverg",
    "galápagos",
    "gulltop",
    "guløye",
    "horn",
    "humboldt",
    "hvitkinn",
    "kap",
    "keiser",
    "klippehopper",
    "konge",
    "langdusk",
    "magellan",
    "ring",
    "skog",
    "snares",
    "kode",
    "pode",
    "smart",
    "humor",
    "jule",
    "fjøs",
    "øl",
    "vin",
    "løpe",
    "party",
    "intern",
    "kaffe",
    "te",
    "kake",
    "pizza",
    "burger",
    "pasta",
    "taco",
    "sushi",
    "standup",
    "konsert",
    "quiz",
    "mikro",
    "økonomi",
    "fysikk",
    "matte",
    "kjemi",
    "biologi",
    "informatikk",
    "humaniora",
    "kor",
    "mugge",
]


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


class MobileCardRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    group: str
    discount_level: int | None = None
    pingvin_points: int = 0
    signed_contract: bool = False


class MobileCardRoleHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    group: str
    discount_level: int | None = None
    pingvin_points: int = 0
    signed_contract: bool = False
    year: int
    term: int
    semester: str
    is_active: bool = False


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
    role_history: list[MobileCardRoleHistory] | None = None
    word_of_the_day: str

    def to_legacy_dict(self) -> dict:
        payload = {
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

        if self.role_history is not None:
            payload["vervHistorikk"] = [
                {
                    "navn": role.name,
                    "gruppe": role.group,
                    "rabattTrinn": role.discount_level,
                    "pingvinPoeng": role.pingvin_points,
                    "signertKontrakt": role.signed_contract,
                    "ar": role.year,
                    "semester": role.semester,
                    "aktiv": role.is_active,
                    "startet": None,
                    "sluttet": None,
                }
                for role in self.role_history
            ]

        return payload


@dataclass(slots=True)
class MobileCardSession:
    session_token: str
    card: MobileCardResponse


@dataclass(slots=True)
class MobileCardCurrentCardResult:
    card: MobileCardResponse
    renewed_session_token: str | None = None


@dataclass(slots=True)
class DecodedMobileCardSession:
    age_seconds: int
    is_review: bool
    person_id: int | None
    remaining_seconds: int


class MobileCardService:
    def __init__(
        self,
        settings: Settings,
        repository: MobileCardRepository,
        email_sender: EmailSenderProtocol,
        media_token_service: MediaTokenService | None = None,
        april_state_service: MobileCardAprilStateService | None = None,
        email_template_renderer: MobileCardEmailTemplateRendererProtocol | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.email_sender = email_sender
        self.media_token_service = media_token_service
        self.april_state_service = april_state_service
        self.email_template_renderer = (
            email_template_renderer or MobileCardEmailTemplateRenderer()
        )
        self.serializer = URLSafeTimedSerializer(
            settings.app_secret_key, salt="kvarteret-mobile-card"
        )
        self._access_code_request_counts: TTLCache[str, int] = TTLCache(
            ttl_seconds=settings.mobile_card_access_code_request_window_seconds,
            max_entries=4096,
        )
        self._session_attempt_counts: TTLCache[str, int] = TTLCache(
            ttl_seconds=settings.mobile_card_session_attempt_window_seconds,
            max_entries=4096,
        )

    async def request_access_code(
        self, email: str, *, source_key: str | None = None
    ) -> None:
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
            and now - existing_created_at
            <= timedelta(seconds=self.settings.mobile_card_access_code_cooldown_seconds)
        ):
            access_code = str(existing_access_code)
            logger.info(
                "Reused recent mobile-card access code for volunteer %s",
                volunteer_row["id"],
            )
        else:
            access_code = _generate_access_code()
            await self.repository.store_access_code(
                volunteer_id=volunteer_row["id"],
                access_code=access_code,
                created_at=now,
            )
            logger.info(
                "Generated mobile-card access code for volunteer %s",
                volunteer_row["id"],
            )

        rendered_email = self.email_template_renderer.render_access_code_email(
            access_code=access_code,
            expires_in_minutes=self.settings.mobile_card_access_code_ttl_minutes,
        )
        try:
            await self.email_sender.send_email(
                recipient_email=email.strip(),
                subject=rendered_email.subject,
                html_body=rendered_email.html_body,
            )
        except SmtpDeliveryError:
            logger.exception(
                "Failed to deliver access code email for volunteer %s",
                volunteer_row["id"],
            )
            raise MobileCardError(
                "Could not send access code email. Please try again later."
            )
        logger.info(
            "Sent mobile-card access code email for volunteer %s", volunteer_row["id"]
        )
        return None

    async def create_session(
        self,
        email: str,
        access_code: str,
        *,
        include_role_history: bool = False,
        source_key: str | None = None,
    ) -> MobileCardSession:
        normalized_email = email.strip().lower()
        normalized_access_code = access_code.strip()
        if self._is_review_request(normalized_email, normalized_access_code):
            card = self._build_review_card(include_role_history=include_role_history)
            token = self._build_session_token({"person_id": 0, "review": True})
            return MobileCardSession(session_token=token, card=card)
        attempt_keys = _build_rate_limit_keys(normalized_email, source_key)
        self._enforce_rate_limit(
            cache=self._session_attempt_counts,
            keys=attempt_keys,
            limit=self.settings.mobile_card_session_attempt_limit,
            message="Too many access-code attempts. Try again later.",
        )

        # Increment rate limit BEFORE validation to prevent TOCTOU races.
        self._increment_rate_limit(self._session_attempt_counts, attempt_keys)

        volunteer_row = await self.repository.find_volunteer_by_email_and_code(
            email=normalized_email,
            access_code=normalized_access_code,
            expires_after=datetime.now(UTC)
            - timedelta(minutes=self.settings.mobile_card_access_code_ttl_minutes),
        )
        if volunteer_row is None:
            raise MobileCardInvalidAccessCodeError("Invalid access code.")
        self._clear_rate_limit(self._session_attempt_counts, attempt_keys)
        token = self._build_session_token({"person_id": volunteer_row["id"]})
        card = await self._build_card(
            volunteer_row["id"], include_role_history=include_role_history
        )
        return MobileCardSession(session_token=token, card=card)

    async def get_current_card(
        self, session_token: str, *, include_role_history: bool = False
    ) -> MobileCardCurrentCardResult:
        decoded = self._decode_session_token(session_token)

        if decoded.is_review:
            card = self._build_review_card(include_role_history=include_role_history)
        else:
            card = await self._build_card(
                decoded.person_id or 0, include_role_history=include_role_history
            )

        renewed_session_token = self._maybe_renew_session_token(decoded)
        return MobileCardCurrentCardResult(
            card=card,
            renewed_session_token=renewed_session_token,
        )

    async def _build_card(
        self, volunteer_id: int, *, include_role_history: bool = False
    ) -> MobileCardResponse:
        current_semester = get_current_semester_code()
        snapshot = await self.repository.fetch_card_snapshot(
            volunteer_id=volunteer_id,
            semester_code=current_semester,
            include_role_history=include_role_history,
        )
        if snapshot is None:
            raise MobileCardPersonNotFoundError(
                f"Volunteer {volunteer_id} was not found."
            )
        return await self._build_card_response(
            snapshot, include_role_history=include_role_history
        )

    async def _build_card_response(
        self, snapshot: MobileCardSnapshot, *, include_role_history: bool = False
    ) -> MobileCardResponse:
        photo_url = (
            self.media_token_service.build_photo_media_url(snapshot.photo_path)
            if snapshot.photo_path and self.media_token_service is not None
            else None
        )
        if (
            self.april_state_service is not None
            and await self.april_state_service.is_enabled()
        ):
            photo_url = self._build_april_photo_url(snapshot)
        return MobileCardResponse(
            person_id=snapshot.volunteer_id,
            first_name=snapshot.first_name,
            last_name=snapshot.last_name,
            birth_date=snapshot.birth_date,
            created_at=snapshot.created_at,
            valid_until=datetime.now(UTC)
            + timedelta(days=self.settings.mobile_card_session_ttl_days),
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
            role_history=(
                [
                    MobileCardRoleHistory(
                        name=role.name,
                        group=role.group,
                        discount_level=role.discount_level,
                        pingvin_points=role.pingvin_points,
                        signed_contract=role.signed_contract,
                        year=role.semester // 10,
                        term=role.semester % 10,
                        semester=_semester_label(role.semester),
                        is_active=role.is_active,
                    )
                    for role in snapshot.role_history
                ]
                if include_role_history
                else None
            ),
            word_of_the_day=_word_of_the_day(),
        )

    def _build_april_photo_url(self, snapshot: MobileCardSnapshot) -> str:
        filename = _APRIL_FOOLS_DEFAULT_IMAGE
        for role in snapshot.active_roles:
            mapped_filename = _APRIL_FOOLS_IMAGE_BY_GROUP_ID.get(role.group_id)
            if mapped_filename is not None:
                filename = mapped_filename
                break
        prefix = (
            self.settings.app_public_base_url.rstrip("/")
            if self.settings.app_public_base_url
            else ""
        )
        return f"{prefix}/static/images/april/{filename}"

    def _build_session_token(self, payload: dict[str, int | bool]) -> str:
        return self.serializer.dumps(payload)

    def _decode_session_token(self, session_token: str) -> DecodedMobileCardSession:
        now = datetime.now(UTC)

        try:
            payload, issued_at = self.serializer.loads(
                session_token,
                max_age=self._session_ttl_seconds(),
                return_timestamp=True,
            )
        except SignatureExpired as exc:
            self._log_invalid_session("expired")
            raise MobileCardInvalidSessionError(
                _UNKNOWN_SESSION_TOKEN, reason="expired"
            ) from exc
        except BadSignature as exc:
            self._log_invalid_session("bad_signature")
            raise MobileCardInvalidSessionError(
                _UNKNOWN_SESSION_TOKEN,
                reason="bad_signature",
            ) from exc

        if not isinstance(payload, dict):
            self._log_invalid_session("malformed")
            raise MobileCardInvalidSessionError(
                _UNKNOWN_SESSION_TOKEN, reason="malformed"
            )

        is_review = payload.get("review") is True
        person_id = payload.get("person_id")

        if not is_review and not isinstance(person_id, int):
            self._log_invalid_session("malformed")
            raise MobileCardInvalidSessionError(
                _UNKNOWN_SESSION_TOKEN, reason="malformed"
            )

        age_seconds = max(0, int((now - issued_at).total_seconds()))
        remaining_seconds = max(0, self._session_ttl_seconds() - age_seconds)

        return DecodedMobileCardSession(
            age_seconds=age_seconds,
            is_review=is_review,
            person_id=person_id if isinstance(person_id, int) else None,
            remaining_seconds=remaining_seconds,
        )

    def _maybe_renew_session_token(
        self, decoded: DecodedMobileCardSession
    ) -> str | None:
        if decoded.remaining_seconds > self._session_renewal_threshold_seconds():
            return None

        payload = (
            {"person_id": 0, "review": True}
            if decoded.is_review
            else {"person_id": decoded.person_id or 0}
        )
        renewed_session_token = self._build_session_token(payload)
        logger.info(
            "mobile-card session renewed",
            extra={
                "event": "mobile_card.session.renewed",
                "event_data": {
                    "age_seconds": decoded.age_seconds,
                    "is_review": decoded.is_review,
                    "person_id": decoded.person_id,
                    "remaining_seconds": decoded.remaining_seconds,
                    "renewal_threshold_seconds": self._session_renewal_threshold_seconds(),
                    "ttl_seconds": self._session_ttl_seconds(),
                },
            },
        )
        return renewed_session_token

    def _session_ttl_seconds(self) -> int:
        return self.settings.mobile_card_session_ttl_days * 24 * 3600

    def _session_renewal_threshold_seconds(self) -> int:
        return self.settings.mobile_card_session_renewal_threshold_days * 24 * 3600

    def _log_invalid_session(
        self, reason: Literal["bad_signature", "expired", "malformed"]
    ) -> None:
        logger.warning(
            "mobile-card session invalid",
            extra={
                "event": "mobile_card.session.invalid",
                "event_data": {
                    "reason": reason,
                },
            },
        )

    def _is_review_request(self, email: str, access_code: str | None) -> bool:
        if not self.settings.review_bypass_enabled:
            return False
        if (
            not self.settings.review_bypass_email
            or not self.settings.review_bypass_token
        ):
            return False
        return email == self.settings.review_bypass_email.lower() and (
            access_code is None or access_code == self.settings.review_bypass_token
        )

    def _build_review_card(
        self, *, include_role_history: bool = False
    ) -> MobileCardResponse:
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
            role_history=(
                [
                    MobileCardRoleHistory(
                        name="Guest",
                        group="Kvarteret",
                        discount_level=0,
                        pingvin_points=0,
                        signed_contract=True,
                        year=datetime.now(UTC).year,
                        term=1 if datetime.now(UTC).month <= 6 else 2,
                        semester="Review",
                        is_active=True,
                    )
                ]
                if include_role_history
                else None
            ),
            word_of_the_day=_word_of_the_day(),
        )

    def _enforce_rate_limit(
        self,
        *,
        cache: TTLCache[str, int],
        keys: tuple[str, ...],
        limit: int,
        message: str,
    ) -> None:
        if limit < 1:
            return
        if any((cache.get(key) or 0) >= limit for key in keys):
            raise MobileCardRateLimitedError(message)

    def _increment_rate_limit(
        self, cache: TTLCache[str, int], keys: tuple[str, ...]
    ) -> None:
        for key in keys:
            cache.set(key, (cache.get(key) or 0) + 1)

    def _clear_rate_limit(
        self, cache: TTLCache[str, int], keys: tuple[str, ...]
    ) -> None:
        for key in keys:
            cache.pop(key)


def _generate_access_code(length: int = 6) -> str:
    digits = "0123456789"
    return "".join(choice(digits) for _ in range(length))


def _build_rate_limit_keys(email: str, source_key: str | None) -> tuple[str, ...]:
    keys = [f"email:{email}"]
    if source_key:
        keys.append(f"source:{source_key}")
        keys.append(f"email-source:{email}:{source_key}")
    return tuple(keys)


def _word_of_the_day(now: datetime | None = None) -> str:
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    else:
        current_time = current_time.astimezone(UTC)
    current_day = current_time.date()
    if current_time < datetime.combine(current_day, time(hour=4), tzinfo=UTC):
        current_day -= timedelta(days=1)
    word_index = _daily_word_index(current_day)
    return f"{_LEGACY_PENGUIN_WORD_PREFIXES[word_index]}pingvin"


def _semester_label(semester_code: int) -> str:
    term = semester_code % 10
    if term == 1:
        return "Vår"
    if term == 2:
        return "Høst"
    return str(semester_code)


def _daily_word_index(current_day: date) -> int:
    digest = sha256(current_day.isoformat().encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % len(_LEGACY_PENGUIN_WORD_PREFIXES)
