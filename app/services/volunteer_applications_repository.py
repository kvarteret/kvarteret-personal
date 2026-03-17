from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, insert, select, update

from app.db.session import get_session_factory
from app.db.tables import nytt_personal, personal, personal_bilde, registrering
from app.media_tokens import build_photo_media_url
from app.services.volunteer_applications import (
    VolunteerApplicationDetail,
    VolunteerApplicationListItem,
    VolunteerApplicationInvite,
    VolunteerApplicationSubmissionInput,
)


class VolunteerApplicationsRepository:
    async def create_volunteer_application_invitation(self, *, email: str, token: str) -> VolunteerApplicationInvite:
        async with get_session_factory()() as session:
            async with session.begin():
                row = (
                    await session.execute(
                        insert(registrering)
                        .values(token=token, epost=email)
                        .returning(registrering.c.id, registrering.c.token, registrering.c.epost, registrering.c.opprettet)
                    )
                ).mappings().one()
        return VolunteerApplicationInvite(
            registration_id=row["id"],
            token=row["token"],
            email=row["epost"],
            created_at=row["opprettet"],
        )

    async def list_volunteer_applications(self) -> list[VolunteerApplicationListItem]:
        stmt = (
            select(
                registrering.c.id,
                registrering.c.token,
                registrering.c.epost,
                registrering.c.opprettet,
                nytt_personal.c.id.label("pending_volunteer_id"),
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
            VolunteerApplicationListItem(
                registration_id=row["id"],
                token=row["token"],
                email=row["epost"],
                created_at=row["opprettet"],
                submitted=row["pending_volunteer_id"] is not None,
                first_name=row["fornavn"],
                last_name=row["etternavn"],
                phone=row["telefon"],
            )
            for row in rows
        ]

    async def count_pending_volunteer_applications(self) -> int:
        stmt = select(func.count()).select_from(registrering.join(nytt_personal, nytt_personal.c.registrering_id == registrering.c.id))
        async with get_session_factory()() as session:
            count = await session.scalar(stmt)
        return int(count or 0)

    async def get_volunteer_application_detail(self, registration_id: int) -> VolunteerApplicationDetail | None:
        return await self._get_detail(select(registrering.c.id).where(registrering.c.id == registration_id))

    async def get_volunteer_application_by_token(self, token: str) -> VolunteerApplicationDetail | None:
        return await self._get_detail(select(registrering.c.id).where(registrering.c.token == token))

    async def save_submission(
        self,
        *,
        registration_id: int,
        email: str,
        submission: VolunteerApplicationSubmissionInput,
        photo_sha1: str | None,
        photo_filetype: str | None,
    ) -> None:
        payload = {
            "fornavn": submission.first_name,
            "etternavn": submission.last_name,
            "epost": email,
            "arb_status": submission.employment_status,
            "kjonn": submission.gender,
            "fodselsdato": submission.birth_date,
            "gateadresse": submission.address,
            "postnummerid": submission.postal_code,
            "telefon": submission.phone,
            "photo_sha1": photo_sha1,
            "photo_filetype": photo_filetype,
        }
        async with get_session_factory()() as session:
            async with session.begin():
                existing_row = (
                    await session.execute(
                        select(nytt_personal.c.id).where(nytt_personal.c.registrering_id == registration_id).limit(1)
                    )
                ).mappings().first()
                if existing_row:
                    await session.execute(
                        update(nytt_personal)
                        .where(nytt_personal.c.registrering_id == registration_id)
                        .values(**payload)
                    )
                else:
                    await session.execute(
                        insert(nytt_personal).values(
                            registrering_id=registration_id,
                            **payload,
                        )
                    )

    async def find_volunteer_id_by_email(self, email: str) -> int | None:
        async with get_session_factory()() as session:
            return await session.scalar(
                select(personal.c.id)
                .where(func.lower(func.coalesce(personal.c.epost, "")) == email.lower())
                .limit(1)
            )

    async def approve_volunteer_application(self, registration: VolunteerApplicationDetail) -> int:
        async with get_session_factory()() as session:
            async with session.begin():
                inserted = (
                    await session.execute(
                        insert(personal)
                        .values(
                            fornavn=registration.first_name,
                            etternavn=registration.last_name or "",
                            epost=registration.email,
                            arb_status=registration.employment_status,
                            kjonn=registration.gender or "A",
                            fodselsdato=registration.birth_date,
                            gateadresse=registration.address,
                            postnummerid=registration.postal_code,
                            telefon=registration.phone,
                        )
                        .returning(personal.c.id)
                    )
                ).mappings().one()
                if registration.photo_sha1 and registration.photo_filetype:
                    await session.execute(
                        insert(personal_bilde).values(
                            id_personal=inserted["id"],
                            sha1=registration.photo_sha1,
                            filetype=registration.photo_filetype,
                        )
                    )
                await session.execute(delete(nytt_personal).where(nytt_personal.c.registrering_id == registration.registration_id))
                await session.execute(delete(registrering).where(registrering.c.id == registration.registration_id))
        return inserted["id"]

    async def delete_volunteer_application(self, registration_id: int) -> None:
        async with get_session_factory()() as session:
            async with session.begin():
                await session.execute(delete(nytt_personal).where(nytt_personal.c.registrering_id == registration_id))
                await session.execute(delete(registrering).where(registrering.c.id == registration_id))

    async def _get_detail(self, id_query) -> VolunteerApplicationDetail | None:
        detail_stmt = (
            select(
                registrering.c.id,
                registrering.c.token,
                registrering.c.epost,
                registrering.c.opprettet,
                nytt_personal.c.id.label("pending_volunteer_id"),
                nytt_personal.c.fornavn,
                nytt_personal.c.etternavn,
                nytt_personal.c.telefon,
                nytt_personal.c.fodselsdato,
                nytt_personal.c.kjonn,
                nytt_personal.c.gateadresse,
                nytt_personal.c.postnummerid,
                nytt_personal.c.arb_status,
                nytt_personal.c.photo_sha1,
                nytt_personal.c.photo_filetype,
            )
            .select_from(registrering.outerjoin(nytt_personal, nytt_personal.c.registrering_id == registrering.c.id))
            .where(registrering.c.id.in_(id_query))
            .limit(1)
        )
        async with get_session_factory()() as session:
            row = (await session.execute(detail_stmt)).mappings().first()
        if row is None:
            return None
        return VolunteerApplicationDetail(
            registration_id=row["id"],
            token=row["token"],
            email=row["epost"],
            created_at=row["opprettet"],
            submitted=row["pending_volunteer_id"] is not None,
            pending_volunteer_id=row["pending_volunteer_id"],
            first_name=row["fornavn"],
            last_name=row["etternavn"],
            phone=row["telefon"],
            birth_date=row["fodselsdato"],
            gender=row["kjonn"],
            address=row["gateadresse"],
            postal_code=row["postnummerid"],
            employment_status=row["arb_status"],
            photo_sha1=row["photo_sha1"],
            photo_filetype=row["photo_filetype"],
            photo_url=build_photo_media_url(f"{row['photo_sha1']}.{row['photo_filetype']}")
            if row["photo_sha1"] and row["photo_filetype"]
            else None,
        )
