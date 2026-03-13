from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from secrets import token_urlsafe
from typing import Protocol

from sqlalchemy import delete, func, insert, select, update

from app.db.session import get_session_factory
from app.db.tables import nytt_personal, personal, registrering


class RegistrationError(RuntimeError):
    pass


class RegistrationNotFoundError(RegistrationError):
    pass


class RegistrationConflictError(RegistrationError):
    pass


@dataclass(slots=True)
class RegistrationInvite:
    registration_id: int
    token: str
    email: str
    created_at: datetime


@dataclass(slots=True)
class PendingRegistrationItem:
    registration_id: int
    token: str
    email: str
    created_at: datetime
    submitted: bool
    first_name: str | None
    last_name: str | None
    phone: str | None


@dataclass(slots=True)
class PendingRegistrationDetail:
    registration_id: int
    token: str
    email: str
    created_at: datetime
    submitted: bool
    pending_person_id: int | None
    first_name: str | None
    last_name: str | None
    phone: str | None
    birth_date: date | None
    gender: str | None
    address: str | None
    postal_code: str | None
    employment_status: int | None


@dataclass(slots=True)
class RegistrationSubmissionInput:
    first_name: str | None
    last_name: str
    phone: str | None
    birth_date: date | None
    gender: str
    address: str | None
    postal_code: str | None
    employment_status: int | None


class RegistrationsServiceProtocol(Protocol):
    async def create_invitation(self, email: str) -> RegistrationInvite: ...
    async def list_pending(self) -> list[PendingRegistrationItem]: ...
    async def get_pending_detail(self, registration_id: int) -> PendingRegistrationDetail | None: ...
    async def get_invitation_by_token(self, token: str) -> PendingRegistrationDetail | None: ...
    async def submit_registration(self, token: str, submission: RegistrationSubmissionInput) -> PendingRegistrationDetail: ...
    async def approve_registration(self, registration_id: int) -> int: ...
    async def reject_registration(self, registration_id: int) -> None: ...


class RegistrationsService:
    async def create_invitation(self, email: str) -> RegistrationInvite:
        normalized_email = email.strip().lower()
        if not normalized_email:
            raise RegistrationConflictError("An email address is required.")
        token = token_urlsafe(24)
        async with get_session_factory()() as session:
            async with session.begin():
                row = (
                    await session.execute(
                        insert(registrering)
                        .values(token=token, epost=normalized_email)
                        .returning(registrering.c.id, registrering.c.token, registrering.c.epost, registrering.c.opprettet)
                    )
                ).mappings().one()
        return RegistrationInvite(
            registration_id=row["id"],
            token=row["token"],
            email=row["epost"],
            created_at=row["opprettet"],
        )

    async def list_pending(self) -> list[PendingRegistrationItem]:
        stmt = (
            select(
                registrering.c.id,
                registrering.c.token,
                registrering.c.epost,
                registrering.c.opprettet,
                nytt_personal.c.id.label("pending_person_id"),
                nytt_personal.c.fornavn,
                nytt_personal.c.etternavn,
                nytt_personal.c.telefon,
            )
            .select_from(registrering.outerjoin(nytt_personal, nytt_personal.c.registrering_id == registrering.c.id))
            .order_by(registrering.c.opprettet.desc(), registrering.c.id.desc())
        )
        async with get_session_factory()() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [
            PendingRegistrationItem(
                registration_id=row["id"],
                token=row["token"],
                email=row["epost"],
                created_at=row["opprettet"],
                submitted=row["pending_person_id"] is not None,
                first_name=row["fornavn"],
                last_name=row["etternavn"],
                phone=row["telefon"],
            )
            for row in rows
        ]

    async def get_pending_detail(self, registration_id: int) -> PendingRegistrationDetail | None:
        return await self._get_detail(select(registrering.c.id).where(registrering.c.id == registration_id))

    async def get_invitation_by_token(self, token: str) -> PendingRegistrationDetail | None:
        return await self._get_detail(select(registrering.c.id).where(registrering.c.token == token))

    async def submit_registration(self, token: str, submission: RegistrationSubmissionInput) -> PendingRegistrationDetail:
        existing = await self.get_invitation_by_token(token)
        if existing is None:
            raise RegistrationNotFoundError("Registration token was not found.")

        async with get_session_factory()() as session:
            existing_row = (
                await session.execute(
                    select(nytt_personal.c.id).where(nytt_personal.c.registrering_id == existing.registration_id).limit(1)
                )
            ).mappings().first()
        payload = {
            "fornavn": submission.first_name,
            "etternavn": submission.last_name,
            "epost": existing.email,
            "arb_status": submission.employment_status,
            "kjonn": submission.gender,
            "fodselsdato": submission.birth_date,
            "gateadresse": submission.address,
            "postnummerid": submission.postal_code,
            "telefon": submission.phone,
        }
        async with get_session_factory()() as session:
            async with session.begin():
                if existing_row:
                    await session.execute(
                        update(nytt_personal)
                        .where(nytt_personal.c.registrering_id == existing.registration_id)
                        .values(**payload)
                    )
                else:
                    await session.execute(
                        insert(nytt_personal).values(
                            registrering_id=existing.registration_id,
                            **payload,
                        )
                    )
        detail = await self.get_invitation_by_token(token)
        if detail is None:
            raise RegistrationNotFoundError("Registration token was not found.")
        return detail

    async def approve_registration(self, registration_id: int) -> int:
        detail = await self.get_pending_detail(registration_id)
        if detail is None:
            raise RegistrationNotFoundError("Registration was not found.")
        if detail.pending_person_id is None:
            raise RegistrationConflictError("Registration has not been submitted yet.")

        async with get_session_factory()() as session:
            duplicate_person = await session.scalar(
                select(personal.c.id)
                .where(func.lower(func.coalesce(personal.c.epost, "")) == detail.email.lower())
                .limit(1)
            )
        if duplicate_person is not None:
            raise RegistrationConflictError("A person with this email already exists.")
        async with get_session_factory()() as session:
            async with session.begin():
                inserted = (
                    await session.execute(
                        insert(personal)
                        .values(
                            fornavn=detail.first_name,
                            etternavn=detail.last_name or "",
                            epost=detail.email,
                            arb_status=detail.employment_status,
                            kjonn=detail.gender or "A",
                            fodselsdato=detail.birth_date,
                            gateadresse=detail.address,
                            postnummerid=detail.postal_code,
                            telefon=detail.phone,
                        )
                        .returning(personal.c.id)
                    )
                ).mappings().one()
                await session.execute(delete(nytt_personal).where(nytt_personal.c.registrering_id == registration_id))
                await session.execute(delete(registrering).where(registrering.c.id == registration_id))
        return inserted["id"]

    async def reject_registration(self, registration_id: int) -> None:
        detail = await self.get_pending_detail(registration_id)
        if detail is None:
            raise RegistrationNotFoundError("Registration was not found.")
        async with get_session_factory()() as session:
            async with session.begin():
                await session.execute(delete(nytt_personal).where(nytt_personal.c.registrering_id == registration_id))
                await session.execute(delete(registrering).where(registrering.c.id == registration_id))

    async def _get_detail(self, id_query) -> PendingRegistrationDetail | None:
        detail_stmt = (
            select(
                registrering.c.id,
                registrering.c.token,
                registrering.c.epost,
                registrering.c.opprettet,
                nytt_personal.c.id.label("pending_person_id"),
                nytt_personal.c.fornavn,
                nytt_personal.c.etternavn,
                nytt_personal.c.telefon,
                nytt_personal.c.fodselsdato,
                nytt_personal.c.kjonn,
                nytt_personal.c.gateadresse,
                nytt_personal.c.postnummerid,
                nytt_personal.c.arb_status,
            )
            .select_from(registrering.outerjoin(nytt_personal, nytt_personal.c.registrering_id == registrering.c.id))
            .where(registrering.c.id.in_(id_query))
            .limit(1)
        )
        async with get_session_factory()() as session:
            row = (await session.execute(detail_stmt)).mappings().first()
        if row is None:
            return None
        return PendingRegistrationDetail(
            registration_id=row["id"],
            token=row["token"],
            email=row["epost"],
            created_at=row["opprettet"],
            submitted=row["pending_person_id"] is not None,
            pending_person_id=row["pending_person_id"],
            first_name=row["fornavn"],
            last_name=row["etternavn"],
            phone=row["telefon"],
            birth_date=row["fodselsdato"],
            gender=row["kjonn"],
            address=row["gateadresse"],
            postal_code=row["postnummerid"],
            employment_status=row["arb_status"],
        )


@lru_cache(maxsize=1)
def get_registrations_service() -> RegistrationsService:
    return RegistrationsService()
