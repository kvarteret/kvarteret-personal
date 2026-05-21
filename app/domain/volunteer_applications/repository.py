from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, exists, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repository import SqlAlchemyRepository
from app.db.tables import (
    group_admin_memberships,
    grupper,
    historie,
    nytt_personal,
    personal,
    personal_bilde,
    registrering,
    registrering_gruppe,
    registrering_gruppe_medlem,
    user_accounts,
    verv,
)
from app.domain.volunteer_applications.service import (
    PublicProspectRegistrationResult,
    VolunteerApplicationConflictError,
    VolunteerApplicationDetail,
    VolunteerApplicationFriendInvite,
    VolunteerApplicationGroupMember,
    VolunteerApplicationListItem,
    VolunteerApplicationInvite,
    VolunteerApplicationSubmissionInput,
)
from app.infrastructure.contact.phone_numbers import normalize_phone_number
from app.infrastructure.formatting.semester import get_current_semester_code
from app.media_tokens import MediaTokenService


class VolunteerApplicationsRepository(SqlAlchemyRepository):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        media_token_service: MediaTokenService | None = None,
    ) -> None:
        super().__init__(session_factory=session_factory)
        self.media_token_service = media_token_service

    async def create_public_prospect_registration(
        self,
        *,
        token: str,
        email: str,
        first_name: str | None,
        last_name: str,
        phone: str | None,
        study_institution: str | None,
        background_details: str | None,
        first_choice_group_id: int,
        second_choice_group_id: int | None,
        friend_invites: list[tuple[str, str]] | None = None,
        inviter_name: str | None = None,
        first_choice_group_name: str | None = None,
    ) -> PublicProspectRegistrationResult:
        friend_invites = friend_invites or []
        created_friend_invites: list[VolunteerApplicationFriendInvite] = []
        async with self.session_factory() as session:
            async with session.begin():
                inserted = (
                    await session.execute(
                        insert(registrering)
                        .values(
                            token=token,
                            epost=email,
                            source="public_signup",
                            status="prospect",
                            first_choice_group_id=first_choice_group_id,
                            second_choice_group_id=second_choice_group_id,
                            trial_shift_attended=False,
                        )
                        .returning(registrering.c.id)
                    )
                ).mappings().one()
                group_id: int | None = None
                if friend_invites:
                    group_row = (
                        await session.execute(
                            insert(registrering_gruppe)
                            .values(opprettet=func.now())
                            .returning(registrering_gruppe.c.id)
                        )
                    ).mappings().one()
                    group_id = group_row["id"]
                    await session.execute(
                        insert(registrering_gruppe_medlem).values(
                            gruppe_id=group_id,
                            registrering_id=inserted["id"],
                            registrering_epost=email,
                            rolle="inviter",
                            status="active",
                            opprettet=func.now(),
                        )
                    )
                await session.execute(
                    insert(nytt_personal).values(
                        registrering_id=inserted["id"],
                        fornavn=first_name,
                        etternavn=last_name,
                        epost=email,
                        telefon=normalize_phone_number(phone),
                        kjonn="A",
                        studiested=study_institution,
                        bakgrunn=background_details,
                    )
                )
                for friend_email, friend_token in friend_invites:
                    friend_row = (
                        await session.execute(
                            insert(registrering)
                            .values(
                                token=friend_token,
                                epost=friend_email,
                                source="group_invite",
                                status="invited",
                                first_choice_group_id=first_choice_group_id,
                                second_choice_group_id=second_choice_group_id,
                                trial_shift_attended=False,
                            )
                            .returning(registrering.c.id, registrering.c.token, registrering.c.epost)
                        )
                    ).mappings().one()
                    assert group_id is not None
                    await session.execute(
                        insert(registrering_gruppe_medlem).values(
                            gruppe_id=group_id,
                            registrering_id=friend_row["id"],
                            registrering_epost=friend_row["epost"],
                            rolle="invitee",
                            status="active",
                            opprettet=func.now(),
                        )
                    )
                    created_friend_invites.append(
                        VolunteerApplicationFriendInvite(
                            registration_id=friend_row["id"],
                            token=friend_row["token"],
                            email=friend_row["epost"],
                            inviter_name=inviter_name or email,
                            first_choice_group_name=first_choice_group_name or "",
                        )
                    )
        detail = await self.get_volunteer_application_detail(inserted["id"])
        assert detail is not None
        return PublicProspectRegistrationResult(detail=detail, friend_invites=created_friend_invites)

    async def create_volunteer_application_invitation(
        self,
        *,
        email: str,
        token: str,
        initial_group_id: int | None = None,
        initial_role_id: int | None = None,
    ) -> VolunteerApplicationInvite:
        async with self.session_factory() as session:
            async with session.begin():
                row = (
                    await session.execute(
                        insert(registrering)
                        .values(
                            token=token,
                            epost=email,
                            source="invite",
                            status="invited",
                            initial_group_id=initial_group_id,
                            initial_role_id=initial_role_id,
                            trial_shift_attended=False,
                        )
                        .returning(
                            registrering.c.id,
                            registrering.c.token,
                            registrering.c.epost,
                            registrering.c.opprettet,
                            registrering.c.initial_group_id,
                            registrering.c.initial_role_id,
                        )
                    )
                ).mappings().one()
                names = await self._fetch_assignment_names(
                    session,
                    initial_group_id=row["initial_group_id"],
                    initial_role_id=row["initial_role_id"],
                )
        return VolunteerApplicationInvite(
            registration_id=row["id"],
            token=row["token"],
            email=row["epost"],
            created_at=row["opprettet"],
            initial_group_id=row["initial_group_id"],
            initial_group_name=names["group_name"],
            initial_role_id=row["initial_role_id"],
            initial_role_name=names["role_name"],
        )

    async def list_volunteer_applications(self) -> list[VolunteerApplicationListItem]:
        accepted_group = grupper.alias("accepted_group")
        first_choice_group = grupper.alias("first_choice_group")
        second_choice_group = grupper.alias("second_choice_group")
        accepted_role = verv.alias("accepted_role")
        group_membership = registrering_gruppe_medlem.alias("group_membership")
        stmt = (
            select(
                registrering.c.id,
                registrering.c.token,
                registrering.c.epost,
                registrering.c.opprettet,
                registrering.c.source,
                registrering.c.status,
                registrering.c.initial_group_id,
                registrering.c.initial_role_id,
                registrering.c.first_choice_group_id,
                registrering.c.second_choice_group_id,
                registrering.c.trial_shift_attended,
                registrering.c.full_profile_submitted_at,
                registrering.c.promoted_volunteer_id,
                registrering.c.promoted_at,
                nytt_personal.c.id.label("pending_volunteer_id"),
                nytt_personal.c.fornavn,
                nytt_personal.c.etternavn,
                nytt_personal.c.telefon,
                nytt_personal.c.studiested,
                nytt_personal.c.bakgrunn,
                accepted_group.c.navn.label("initial_group_name"),
                accepted_role.c.verv.label("initial_role_name"),
                first_choice_group.c.navn.label("first_choice_group_name"),
                second_choice_group.c.navn.label("second_choice_group_name"),
                group_membership.c.gruppe_id.label("group_id"),
                group_membership.c.rolle.label("group_role"),
                group_membership.c.status.label("group_status"),
            )
            .select_from(
                registrering.outerjoin(nytt_personal, nytt_personal.c.registrering_id == registrering.c.id)
                .outerjoin(group_membership, group_membership.c.registrering_id == registrering.c.id)
                .outerjoin(accepted_group, accepted_group.c.id == registrering.c.initial_group_id)
                .outerjoin(accepted_role, accepted_role.c.id == registrering.c.initial_role_id)
                .outerjoin(first_choice_group, first_choice_group.c.id == registrering.c.first_choice_group_id)
                .outerjoin(second_choice_group, second_choice_group.c.id == registrering.c.second_choice_group_id)
            )
            .where(registrering.c.promoted_volunteer_id.is_(None))
            .order_by(registrering.c.opprettet.desc(), registrering.c.id.desc())
        )
        async with self.session_factory() as session:
            rows = (await session.execute(stmt)).mappings().all()
        group_ids = {row["group_id"] for row in rows if row["group_id"] is not None}
        group_members_by_id = {
            group_id: await self.list_group_members(group_id)
            for group_id in group_ids
        }
        return [
            VolunteerApplicationListItem(
                registration_id=row["id"],
                token=row["token"],
                email=row["epost"],
                created_at=row["opprettet"],
                submitted=row["full_profile_submitted_at"] is not None,
                source=row["source"],
                status=row["status"],
                pending_volunteer_id=row["pending_volunteer_id"],
                first_name=row["fornavn"],
                last_name=row["etternavn"],
                phone=row["telefon"],
                study_institution=row["studiested"],
                background_details=row["bakgrunn"],
                initial_group_id=row["initial_group_id"],
                initial_group_name=row["initial_group_name"],
                initial_role_id=row["initial_role_id"],
                initial_role_name=row["initial_role_name"],
                first_choice_group_id=row["first_choice_group_id"],
                first_choice_group_name=row["first_choice_group_name"],
                second_choice_group_id=row["second_choice_group_id"],
                second_choice_group_name=row["second_choice_group_name"],
                trial_shift_attended=bool(row["trial_shift_attended"]),
                promoted_volunteer_id=row["promoted_volunteer_id"],
                promoted_at=row["promoted_at"],
                group_id=row["group_id"],
                group_role=row["group_role"],
                group_status=row["group_status"],
                group_members=group_members_by_id.get(row["group_id"]),
            )
            for row in rows
        ]

    async def list_recent_volunteer_registrations(
        self,
        *,
        limit: int,
        before_volunteer_id: int | None = None,
    ) -> list[dict]:
        latest_assignment_rank = func.row_number().over(
            partition_by=historie.c.id_personal,
            order_by=(historie.c.id.desc(),),
        ).label("assignment_rank")
        latest_assignment_rows = (
            select(
                historie.c.id_personal.label("id_personal"),
                historie.c.id_gruppe.label("latest_group_id"),
                historie.c.id_verv.label("latest_role_id"),
                historie.c.semester.label("latest_semester_code"),
                latest_assignment_rank,
            )
        ).subquery()
        latest_assignment = (
            select(
                latest_assignment_rows.c.id_personal,
                latest_assignment_rows.c.latest_group_id,
                latest_assignment_rows.c.latest_role_id,
                latest_assignment_rows.c.latest_semester_code,
            )
            .where(latest_assignment_rows.c.assignment_rank == 1)
        ).subquery()
        stmt = (
            select(
                personal.c.id,
                personal.c.fornavn,
                personal.c.etternavn,
                personal.c.epost,
                personal.c.telefon,
                personal.c.opprettet,
                latest_assignment.c.latest_semester_code,
                grupper.c.navn.label("latest_group_name"),
                verv.c.verv.label("latest_role_name"),
                personal_bilde.c.sha1.label("photo_sha1"),
                personal_bilde.c.filetype.label("photo_filetype"),
                registrering.c.id.label("registration_id"),
                registrering_gruppe_medlem.c.gruppe_id.label("group_id"),
                registrering_gruppe_medlem.c.rolle.label("group_role"),
                registrering_gruppe_medlem.c.status.label("group_status"),
            )
            .select_from(
                personal.outerjoin(latest_assignment, latest_assignment.c.id_personal == personal.c.id)
                .outerjoin(grupper, grupper.c.id == latest_assignment.c.latest_group_id)
                .outerjoin(verv, verv.c.id == latest_assignment.c.latest_role_id)
                .outerjoin(personal_bilde, personal_bilde.c.id_personal == personal.c.id)
                .outerjoin(registrering, registrering.c.promoted_volunteer_id == personal.c.id)
                .outerjoin(registrering_gruppe_medlem, registrering_gruppe_medlem.c.registrering_id == registrering.c.id)
            )
            .order_by(personal.c.id.desc())
            .limit(limit)
        )
        if before_volunteer_id is not None:
            stmt = stmt.where(personal.c.id < before_volunteer_id)
        async with self.session_factory() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [dict(row) for row in rows]

    async def list_recent_registration_group_members(self, group_id: int) -> list[dict]:
        latest_assignment_rank = func.row_number().over(
            partition_by=historie.c.id_personal,
            order_by=(historie.c.id.desc(),),
        ).label("assignment_rank")
        latest_assignment_rows = (
            select(
                historie.c.id_personal.label("id_personal"),
                historie.c.id_gruppe.label("latest_group_id"),
                historie.c.id_verv.label("latest_role_id"),
                historie.c.semester.label("latest_semester_code"),
                latest_assignment_rank,
            )
        ).subquery()
        latest_assignment = (
            select(
                latest_assignment_rows.c.id_personal,
                latest_assignment_rows.c.latest_group_id,
                latest_assignment_rows.c.latest_role_id,
                latest_assignment_rows.c.latest_semester_code,
            )
            .where(latest_assignment_rows.c.assignment_rank == 1)
        ).subquery()
        stmt = (
            select(
                personal.c.id,
                personal.c.fornavn,
                personal.c.etternavn,
                personal.c.epost,
                personal.c.telefon,
                personal.c.opprettet,
                latest_assignment.c.latest_semester_code,
                grupper.c.navn.label("latest_group_name"),
                verv.c.verv.label("latest_role_name"),
                personal_bilde.c.sha1.label("photo_sha1"),
                personal_bilde.c.filetype.label("photo_filetype"),
                registrering.c.id.label("registration_id"),
                registrering_gruppe_medlem.c.gruppe_id.label("group_id"),
                registrering_gruppe_medlem.c.rolle.label("group_role"),
                registrering_gruppe_medlem.c.status.label("group_status"),
            )
            .select_from(
                registrering_gruppe_medlem.join(
                    registrering,
                    registrering.c.id == registrering_gruppe_medlem.c.registrering_id,
                )
                .join(personal, personal.c.id == registrering.c.promoted_volunteer_id)
                .outerjoin(latest_assignment, latest_assignment.c.id_personal == personal.c.id)
                .outerjoin(grupper, grupper.c.id == latest_assignment.c.latest_group_id)
                .outerjoin(verv, verv.c.id == latest_assignment.c.latest_role_id)
                .outerjoin(personal_bilde, personal_bilde.c.id_personal == personal.c.id)
            )
            .where(registrering_gruppe_medlem.c.gruppe_id == group_id)
            .order_by(registrering_gruppe_medlem.c.id.asc())
        )
        async with self.session_factory() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [dict(row) for row in rows]

    async def count_pending_volunteer_applications(self) -> int:
        stmt = (
            select(func.count())
            .select_from(registrering.join(nytt_personal, nytt_personal.c.registrering_id == registrering.c.id))
            .where(registrering.c.promoted_volunteer_id.is_(None))
        )
        async with self.session_factory() as session:
            count = await session.scalar(stmt)
        return int(count or 0)

    async def get_volunteer_application_detail(self, registration_id: int) -> VolunteerApplicationDetail | None:
        return await self._get_detail(select(registrering.c.id).where(registrering.c.id == registration_id))

    async def get_volunteer_application_by_token(self, token: str) -> VolunteerApplicationDetail | None:
        return await self._get_detail(select(registrering.c.id).where(registrering.c.token == token))

    async def find_group_ids_by_names(self, names: list[str]) -> dict[str, int]:
        if not names:
            return {}
        stmt = select(grupper.c.id, grupper.c.navn).where(grupper.c.navn.in_(names))
        async with self.session_factory() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return {row["navn"]: row["id"] for row in rows}

    async def save_submission(
        self,
        *,
        registration_id: int,
        email: str,
        submission: VolunteerApplicationSubmissionInput,
        photo_sha1: str | None,
        photo_filetype: str | None,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                registration_row = (
                    await session.execute(
                        select(registrering.c.promoted_volunteer_id)
                        .where(registrering.c.id == registration_id)
                        .limit(1)
                    )
                ).mappings().first()
                if registration_row is None:
                    return

                volunteer_id = registration_row["promoted_volunteer_id"]
                if volunteer_id is not None:
                    await session.execute(
                        update(personal)
                        .where(personal.c.id == volunteer_id)
                        .values(
                            fornavn=submission.first_name,
                            etternavn=submission.last_name,
                            epost=email,
                            kjonn=submission.gender,
                            fodselsdato=submission.birth_date,
                            gateadresse=submission.address,
                            postnummerid=submission.postal_code,
                            telefon=normalize_phone_number(submission.phone),
                        )
                    )
                    if photo_sha1 and photo_filetype:
                        existing_photo = (
                            await session.execute(
                                select(personal_bilde.c.id_personal)
                                .where(personal_bilde.c.id_personal == volunteer_id)
                                .limit(1)
                            )
                        ).mappings().first()
                        if existing_photo:
                            await session.execute(
                                update(personal_bilde)
                                .where(personal_bilde.c.id_personal == volunteer_id)
                                .values(sha1=photo_sha1, filetype=photo_filetype)
                            )
                        else:
                            await session.execute(
                                insert(personal_bilde).values(
                                    id_personal=volunteer_id,
                                    sha1=photo_sha1,
                                    filetype=photo_filetype,
                                )
                            )
                    await session.execute(
                        update(registrering)
                        .where(registrering.c.id == registration_id)
                        .values(full_profile_submitted_at=func.now())
                    )
                    return

                existing_row = (
                    await session.execute(
                        select(nytt_personal.c.id, nytt_personal.c.studiested, nytt_personal.c.bakgrunn)
                        .where(nytt_personal.c.registrering_id == registration_id)
                        .limit(1)
                    )
                ).mappings().first()
                payload = {
                    "fornavn": submission.first_name,
                    "etternavn": submission.last_name,
                    "epost": email,
                    "kjonn": submission.gender,
                    "fodselsdato": submission.birth_date,
                    "gateadresse": submission.address,
                    "postnummerid": submission.postal_code,
                    "telefon": normalize_phone_number(submission.phone),
                    "photo_sha1": photo_sha1,
                    "photo_filetype": photo_filetype,
                    "studiested": existing_row["studiested"] if existing_row else None,
                    "bakgrunn": existing_row["bakgrunn"] if existing_row else None,
                }
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
                await session.execute(
                    update(registrering)
                    .where(registrering.c.id == registration_id)
                    .values(status="submitted", full_profile_submitted_at=func.now())
                )

    async def set_trial_shift_attended(self, registration_id: int, *, attended: bool) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(registrering)
                    .where(registrering.c.id == registration_id)
                    .values(
                        trial_shift_attended=attended,
                        trial_shift_marked_at=datetime.now(UTC) if attended else None,
                    )
                )

    async def find_volunteer_id_by_email(self, email: str) -> int | None:
        async with self.session_factory() as session:
            return await session.scalar(
                select(personal.c.id)
                .where(func.lower(func.coalesce(personal.c.epost, "")) == email.lower())
                .limit(1)
            )

    async def find_active_registration_id_by_email(self, email: str) -> int | None:
        async with self.session_factory() as session:
            return await session.scalar(
                select(registrering.c.id)
                .where(
                    func.lower(func.coalesce(registrering.c.epost, "")) == email.lower(),
                    registrering.c.promoted_volunteer_id.is_(None),
                    registrering.c.status != "rejected",
                )
                .limit(1)
            )

    async def list_group_members(
        self,
        group_id: int,
        *,
        include_dropped: bool = True,
    ) -> list[VolunteerApplicationGroupMember]:
        stmt = (
            select(
                registrering_gruppe_medlem.c.gruppe_id,
                registrering_gruppe_medlem.c.registrering_id,
                registrering_gruppe_medlem.c.registrering_epost,
                registrering_gruppe_medlem.c.rolle,
                registrering_gruppe_medlem.c.status,
                registrering_gruppe_medlem.c.droppet,
                registrering.c.full_profile_submitted_at,
                registrering.c.trial_shift_attended,
                registrering.c.promoted_volunteer_id,
                nytt_personal.c.id.label("pending_volunteer_id"),
                nytt_personal.c.fornavn,
                nytt_personal.c.etternavn,
            )
            .select_from(
                registrering_gruppe_medlem.outerjoin(
                    registrering,
                    registrering.c.id == registrering_gruppe_medlem.c.registrering_id,
                ).outerjoin(nytt_personal, nytt_personal.c.registrering_id == registrering.c.id)
            )
            .where(registrering_gruppe_medlem.c.gruppe_id == group_id)
            .order_by(registrering_gruppe_medlem.c.id.asc())
        )
        if not include_dropped:
            stmt = stmt.where(registrering_gruppe_medlem.c.status == "active")
        async with self.session_factory() as session:
            rows = (await session.execute(stmt)).mappings().all()
        return [
            VolunteerApplicationGroupMember(
                group_id=row["gruppe_id"],
                registration_id=row["registrering_id"],
                email=row["registrering_epost"],
                role=row["rolle"],
                status=row["status"],
                submitted=row["full_profile_submitted_at"] is not None,
                pending_volunteer_id=row["pending_volunteer_id"],
                first_name=row["fornavn"],
                last_name=row["etternavn"],
                trial_shift_attended=bool(row["trial_shift_attended"]),
                promoted_volunteer_id=row["promoted_volunteer_id"],
                dropped_at=row["droppet"],
            )
            for row in rows
        ]

    async def list_group_admin_email_recipients(self, group_id: int) -> list[str]:
        stmt = (
            select(func.lower(user_accounts.c.email).label("email"))
            .select_from(
                group_admin_memberships.join(
                    user_accounts,
                    user_accounts.c.auth_user_id == group_admin_memberships.c.auth_user_id,
                )
            )
            .where(
                group_admin_memberships.c.gruppe_id == group_id,
                user_accounts.c.email.is_not(None),
                user_accounts.c.email != "",
            )
            .distinct()
            .order_by(func.lower(user_accounts.c.email))
        )
        async with self.session_factory() as session:
            return [row for row in await session.scalars(stmt)]

    async def approve_volunteer_application(
        self,
        registration: VolunteerApplicationDetail,
        *,
        accepted_group_id: int | None,
    ) -> int:
        async with self.session_factory() as session:
            async with session.begin():
                if registration.initial_role_id is not None and accepted_group_id is not None:
                    role_match = await session.scalar(
                        select(
                            exists().where(
                                verv.c.id == registration.initial_role_id,
                                verv.c.id_gruppe == accepted_group_id,
                            )
                        )
                    )
                    if not role_match:
                        raise VolunteerApplicationConflictError(
                            "The selected initial verv is no longer valid for the chosen group."
                        )
                inserted = (
                    await session.execute(
                        insert(personal)
                        .values(
                            fornavn=registration.first_name,
                            etternavn=registration.last_name or "",
                            epost=registration.email,
                            kjonn=registration.gender or "A",
                            fodselsdato=registration.birth_date,
                            gateadresse=registration.address,
                            postnummerid=registration.postal_code,
                            telefon=normalize_phone_number(registration.phone),
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
                if accepted_group_id is not None:
                    await session.execute(
                        insert(historie).values(
                            id_personal=inserted["id"],
                            id_gruppe=accepted_group_id,
                            id_verv=registration.initial_role_id,
                            semester=get_current_semester_code(),
                            signert_kontrakt=False,
                        )
                    )
                await session.execute(
                    update(registrering)
                    .where(registrering.c.id == registration.registration_id)
                    .values(
                        promoted_volunteer_id=inserted["id"],
                        promoted_at=func.now(),
                        status="promoted",
                        initial_group_id=accepted_group_id,
                    )
                )
        return inserted["id"]

    async def delete_volunteer_application(self, registration_id: int) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                await session.execute(delete(nytt_personal).where(nytt_personal.c.registrering_id == registration_id))
                await session.execute(delete(registrering).where(registrering.c.id == registration_id))

    async def drop_group_invitee(
        self,
        registration_id: int,
        *,
        dropped_by_user_id: int | None = None,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(registrering_gruppe_medlem)
                    .where(
                        registrering_gruppe_medlem.c.registrering_id == registration_id,
                        registrering_gruppe_medlem.c.rolle == "invitee",
                        registrering_gruppe_medlem.c.status == "active",
                    )
                    .values(
                        status="dropped",
                        droppet=func.now(),
                        droppet_av_user_id=dropped_by_user_id,
                    )
                )

    async def _get_detail(self, id_query) -> VolunteerApplicationDetail | None:
        accepted_group = grupper.alias("accepted_group")
        first_choice_group = grupper.alias("first_choice_group")
        second_choice_group = grupper.alias("second_choice_group")
        accepted_role = verv.alias("accepted_role")
        group_membership = registrering_gruppe_medlem.alias("group_membership")
        detail_stmt = (
            select(
                registrering.c.id,
                registrering.c.token,
                registrering.c.epost,
                registrering.c.opprettet,
                registrering.c.source,
                registrering.c.status,
                registrering.c.initial_group_id,
                registrering.c.initial_role_id,
                registrering.c.first_choice_group_id,
                registrering.c.second_choice_group_id,
                registrering.c.trial_shift_attended,
                registrering.c.trial_shift_marked_at,
                registrering.c.full_profile_submitted_at,
                registrering.c.promoted_volunteer_id,
                registrering.c.promoted_at,
                nytt_personal.c.id.label("pending_volunteer_id"),
                nytt_personal.c.fornavn,
                nytt_personal.c.etternavn,
                nytt_personal.c.telefon,
                nytt_personal.c.fodselsdato,
                nytt_personal.c.kjonn,
                nytt_personal.c.gateadresse,
                nytt_personal.c.postnummerid,
                nytt_personal.c.photo_sha1,
                nytt_personal.c.photo_filetype,
                nytt_personal.c.studiested,
                nytt_personal.c.bakgrunn,
                accepted_group.c.navn.label("initial_group_name"),
                accepted_role.c.verv.label("initial_role_name"),
                first_choice_group.c.navn.label("first_choice_group_name"),
                second_choice_group.c.navn.label("second_choice_group_name"),
                group_membership.c.gruppe_id.label("group_id"),
                group_membership.c.rolle.label("group_role"),
                group_membership.c.status.label("group_status"),
            )
            .select_from(
                registrering.outerjoin(nytt_personal, nytt_personal.c.registrering_id == registrering.c.id)
                .outerjoin(group_membership, group_membership.c.registrering_id == registrering.c.id)
                .outerjoin(accepted_group, accepted_group.c.id == registrering.c.initial_group_id)
                .outerjoin(accepted_role, accepted_role.c.id == registrering.c.initial_role_id)
                .outerjoin(first_choice_group, first_choice_group.c.id == registrering.c.first_choice_group_id)
                .outerjoin(second_choice_group, second_choice_group.c.id == registrering.c.second_choice_group_id)
            )
            .where(registrering.c.id.in_(id_query))
            .limit(1)
        )
        async with self.session_factory() as session:
            row = (await session.execute(detail_stmt)).mappings().first()
        if row is None:
            return None
        group_members = await self.list_group_members(row["group_id"]) if row["group_id"] is not None else None
        return VolunteerApplicationDetail(
            registration_id=row["id"],
            token=row["token"],
            email=row["epost"],
            created_at=row["opprettet"],
            submitted=row["full_profile_submitted_at"] is not None,
            source=row["source"],
            status=row["status"],
            pending_volunteer_id=row["pending_volunteer_id"],
            first_name=row["fornavn"],
            last_name=row["etternavn"],
            phone=row["telefon"],
            birth_date=row["fodselsdato"],
            gender=row["kjonn"],
            address=row["gateadresse"],
            postal_code=row["postnummerid"],
            photo_sha1=row["photo_sha1"],
            photo_filetype=row["photo_filetype"],
            photo_url=(
                self.media_token_service.build_photo_media_url(f"{row['photo_sha1']}.{row['photo_filetype']}")
                if row["photo_sha1"] and row["photo_filetype"] and self.media_token_service is not None
                else None
            ),
            study_institution=row["studiested"],
            background_details=row["bakgrunn"],
            initial_group_id=row["initial_group_id"],
            initial_group_name=row["initial_group_name"],
            initial_role_id=row["initial_role_id"],
            initial_role_name=row["initial_role_name"],
            first_choice_group_id=row["first_choice_group_id"],
            first_choice_group_name=row["first_choice_group_name"],
            second_choice_group_id=row["second_choice_group_id"],
            second_choice_group_name=row["second_choice_group_name"],
            trial_shift_attended=bool(row["trial_shift_attended"]),
            trial_shift_marked_at=row["trial_shift_marked_at"],
            promoted_volunteer_id=row["promoted_volunteer_id"],
            promoted_at=row["promoted_at"],
            group_id=row["group_id"],
            group_role=row["group_role"],
            group_status=row["group_status"],
            group_members=group_members,
        )

    async def _fetch_assignment_names(
        self,
        session: AsyncSession,
        *,
        initial_group_id: int | None,
        initial_role_id: int | None,
    ) -> dict[str, str | None]:
        if initial_group_id is None and initial_role_id is None:
            return {"group_name": None, "role_name": None}
        row = (
            await session.execute(
                select(grupper.c.navn.label("group_name"), verv.c.verv.label("role_name"))
                .select_from(grupper.outerjoin(verv, verv.c.id == initial_role_id))
                .where(grupper.c.id == initial_group_id)
                .limit(1)
            )
        ).mappings().first()
        if row is None:
            return {"group_name": None, "role_name": None}
        return {"group_name": row["group_name"], "role_name": row["role_name"]}
