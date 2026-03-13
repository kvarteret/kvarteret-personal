from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from secrets import choice

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, update

from app.config import Settings, get_settings
from app.db.session import get_session_factory
from app.db.tables import grupper, historie, personal, personal_bilde, verv
from app.media_tokens import build_photo_media_url
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


class MobileCardRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    group: str
    discount_level: int | None = None
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
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.serializer = URLSafeTimedSerializer(settings.app_secret_key, salt="kvarteret-mobile-card")

    async def request_access_code(self, email: str) -> None:
        normalized_email = email.strip().lower()
        if self._is_review_request(normalized_email, None):
            return None

        people = await self._get_people_by_email(normalized_email)
        if len(people) > 1:
            raise MobileCardDuplicatePersonError(
                "More than one person uses this email address. Contact an administrator."
            )
        if not people:
            raise MobileCardPersonNotFoundError(
                "Email not found in the personnel database."
            )

        person_row = people[0]
        now = datetime.now(UTC)
        existing_created_at = person_row["internkort_access_token_created_at"]
        if existing_created_at and now - existing_created_at <= timedelta(
            seconds=self.settings.mobile_card_access_code_cooldown_seconds
        ):
            logger.info("Reused recent mobile-card access code for person %s", person_row["id"])
            return None

        access_code = _generate_access_code()
        async with get_session_factory()() as session:
            async with session.begin():
                await session.execute(
                    update(personal)
                    .where(personal.c.id == person_row["id"])
                    .values(
                        internkortaccesstoken=access_code,
                        internkort_access_token_created_at=now,
                    )
                )
        logger.info("Generated mobile-card access code for person %s", person_row["id"])
        return None

    async def create_session(self, email: str, access_code: str) -> MobileCardSession:
        normalized_email = email.strip().lower()
        if self._is_review_request(normalized_email, access_code):
            card = self._build_review_card()
            token = self.serializer.dumps({"person_id": 0, "review": True})
            return MobileCardSession(session_token=token, card=card)

        person_row = await self._get_person_by_email_and_code(normalized_email, access_code)
        if person_row is None:
            raise MobileCardInvalidAccessCodeError("Invalid access code.")
        token = self.serializer.dumps({"person_id": person_row["id"]})
        card = await self._build_card(person_row["id"])
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

    async def _get_people_by_email(self, email: str) -> list[dict]:
        stmt = (
            select(
                personal.c.id,
                personal.c.fornavn,
                personal.c.etternavn,
                personal.c.internkortaccesstoken,
                personal.c.internkort_access_token_created_at,
            )
            .where(func.lower(func.coalesce(personal.c.epost, "")) == email)
            .order_by(personal.c.id.asc())
        )
        async with get_session_factory()() as session:
            return list((await session.execute(stmt)).mappings().all())

    async def _get_person_by_email_and_code(self, email: str, access_code: str) -> dict | None:
        expires_after = datetime.now(UTC) - timedelta(minutes=self.settings.mobile_card_access_code_ttl_minutes)
        stmt = (
            select(personal.c.id)
            .where(func.lower(func.coalesce(personal.c.epost, "")) == email)
            .where(personal.c.internkortaccesstoken == access_code)
            .where(personal.c.internkort_access_token_created_at.is_not(None))
            .where(personal.c.internkort_access_token_created_at >= expires_after)
            .limit(1)
        )
        async with get_session_factory()() as session:
            return (await session.execute(stmt)).mappings().first()

    async def _build_card(self, person_id: int) -> MobileCardResponse:
        person_stmt = (
            select(
                personal.c.id,
                personal.c.fornavn,
                personal.c.etternavn,
                personal.c.fodselsdato,
                personal.c.opprettet,
                personal_bilde.c.sha1,
                personal_bilde.c.filetype,
            )
            .select_from(personal.outerjoin(personal_bilde, personal_bilde.c.id_personal == personal.c.id))
            .where(personal.c.id == person_id)
            .limit(1)
        )
        points_stmt = (
            select(func.coalesce(func.sum(verv.c.pingvinpoeng), 0).label("pingvin_points"))
            .select_from(historie.outerjoin(verv, verv.c.id == historie.c.id_verv))
            .where(historie.c.id_personal == person_id)
        )
        current_semester = get_current_semester_code()
        active_roles_stmt = (
            select(
                verv.c.verv.label("verv_navn"),
                grupper.c.navn.label("gruppe_navn"),
                grupper.c.rabatt_trinn,
                historie.c.signert_kontrakt,
            )
            .select_from(
                historie.join(verv, verv.c.id == historie.c.id_verv).join(grupper, grupper.c.id == historie.c.id_gruppe)
            )
            .where(historie.c.id_personal == person_id)
            .where(historie.c.semester == current_semester)
            .order_by(grupper.c.navn.asc(), verv.c.verv.asc())
        )
        async with get_session_factory()() as session:
            person_row = (await session.execute(person_stmt)).mappings().first()
            if person_row is None:
                raise MobileCardPersonNotFoundError(f"Person {person_id} was not found.")
            pingvin_points = int((await session.execute(points_stmt)).scalar_one() or 0)
            active_role_rows = (await session.execute(active_roles_stmt)).mappings().all()

        photo_url = None
        if person_row["sha1"] and person_row["filetype"]:
            photo_url = build_photo_media_url(f"{person_row['sha1']}.{person_row['filetype']}")

        return MobileCardResponse(
            person_id=person_row["id"],
            first_name=person_row["fornavn"] or "",
            last_name=person_row["etternavn"],
            birth_date=person_row["fodselsdato"],
            created_at=person_row["opprettet"],
            valid_until=datetime.now(UTC) + timedelta(days=self.settings.mobile_card_session_ttl_days),
            photo_url=photo_url,
            pingvin_points=pingvin_points,
            active_roles=[
                MobileCardRole(
                    name=row["verv_navn"],
                    group=row["gruppe_navn"],
                    discount_level=row["rabatt_trinn"],
                    signed_contract=row["signert_kontrakt"],
                )
                for row in active_role_rows
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
                    signed_contract=True,
                )
            ],
            word_of_the_day=_word_of_the_day(),
        )


def _generate_access_code(length: int = 6) -> str:
    digits = "0123456789"
    return "".join(choice(digits) for _ in range(length))


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


@lru_cache(maxsize=1)
def get_mobile_card_service() -> MobileCardService:
    return MobileCardService(get_settings())
