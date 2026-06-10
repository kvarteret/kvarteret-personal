from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


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
