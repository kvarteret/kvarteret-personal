from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, exists, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import SqlAlchemyRepository
from app.db.tables import (
    group_admin_memberships,
    groups,
    role_assignments,
    volunteer_application_submissions,
    volunteer_records,
    volunteer_photos,
    volunteer_application_invites,
    volunteer_application_groups,
    volunteer_application_group_members,
    user_accounts,
    assignment_roles,
)
from app.domain.volunteer_applications.state_machine import (
    ApplicationState,
    DomainEventRecord,
    MembershipState,
)
from app.domain.volunteer_applications.tables import domain_events
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
    def __init__(self, media_token_service: MediaTokenService | None = None) -> None:
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
        session = self.session
        inserted = (
            (
                await session.execute(
                    insert(volunteer_application_invites)
                    .values(
                        token=token,
                        email=email,
                        source="public_signup",
                        status=ApplicationState.PROSPECT,
                        first_choice_group_id=first_choice_group_id,
                        second_choice_group_id=second_choice_group_id,
                        trial_shift_attended=False,
                    )
                    .returning(volunteer_application_invites.c.id)
                )
            )
            .mappings()
            .one()
        )
        group_id: int | None = None
        if friend_invites:
            group_row = (
                (
                    await session.execute(
                        insert(volunteer_application_groups)
                        .values(created_at=func.now())
                        .returning(volunteer_application_groups.c.id)
                    )
                )
                .mappings()
                .one()
            )
            group_id = group_row["id"]
            await session.execute(
                insert(volunteer_application_group_members).values(
                    group_id=group_id,
                    invite_id=inserted["id"],
                    applicant_email=email,
                    role="inviter",
                    status=MembershipState.ACTIVE,
                    created_at=func.now(),
                )
            )
        await session.execute(
            insert(volunteer_application_submissions).values(
                invite_id=inserted["id"],
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=normalize_phone_number(phone),
                gender="A",
                studiested=study_institution,
                bakgrunn=background_details,
            )
        )
        for friend_email, friend_token in friend_invites:
            friend_row = (
                (
                    await session.execute(
                        insert(volunteer_application_invites)
                        .values(
                            token=friend_token,
                            email=friend_email,
                            source="group_invite",
                            status=ApplicationState.INVITED,
                            first_choice_group_id=first_choice_group_id,
                            second_choice_group_id=second_choice_group_id,
                            trial_shift_attended=False,
                        )
                        .returning(
                            volunteer_application_invites.c.id,
                            volunteer_application_invites.c.token,
                            volunteer_application_invites.c.email,
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert group_id is not None
            await session.execute(
                insert(volunteer_application_group_members).values(
                    group_id=group_id,
                    invite_id=friend_row["id"],
                    applicant_email=friend_row["email"],
                    role="invitee",
                    status=MembershipState.ACTIVE,
                    created_at=func.now(),
                )
            )
            created_friend_invites.append(
                VolunteerApplicationFriendInvite(
                    registration_id=friend_row["id"],
                    token=friend_row["token"],
                    email=friend_row["email"],
                    inviter_name=inviter_name or email,
                    first_choice_group_name=first_choice_group_name or "",
                )
            )
        detail = await self.get_volunteer_application_detail(inserted["id"])
        assert detail is not None
        return PublicProspectRegistrationResult(
            detail=detail, friend_invites=created_friend_invites
        )

    async def create_volunteer_application_invitation(
        self,
        *,
        email: str,
        token: str,
        initial_group_id: int | None = None,
        initial_role_id: int | None = None,
    ) -> VolunteerApplicationInvite:
        session = self.session
        row = (
            (
                await session.execute(
                    insert(volunteer_application_invites)
                    .values(
                        token=token,
                        email=email,
                        source="invite",
                        status=ApplicationState.INVITED,
                        initial_group_id=initial_group_id,
                        initial_role_id=initial_role_id,
                        trial_shift_attended=False,
                    )
                    .returning(
                        volunteer_application_invites.c.id,
                        volunteer_application_invites.c.token,
                        volunteer_application_invites.c.email,
                        volunteer_application_invites.c.created_at,
                        volunteer_application_invites.c.initial_group_id,
                        volunteer_application_invites.c.initial_role_id,
                    )
                )
            )
            .mappings()
            .one()
        )
        names = await self._fetch_assignment_names(
            session,
            initial_group_id=row["initial_group_id"],
            initial_role_id=row["initial_role_id"],
        )
        return VolunteerApplicationInvite(
            registration_id=row["id"],
            token=row["token"],
            email=row["email"],
            created_at=row["created_at"],
            initial_group_id=row["initial_group_id"],
            initial_group_name=names["group_name"],
            initial_role_id=row["initial_role_id"],
            initial_role_name=names["role_name"],
        )

    async def list_volunteer_applications(self) -> list[VolunteerApplicationListItem]:
        accepted_group = groups.alias("accepted_group")
        first_choice_group = groups.alias("first_choice_group")
        second_choice_group = groups.alias("second_choice_group")
        accepted_role = assignment_roles.alias("accepted_role")
        group_membership = volunteer_application_group_members.alias("group_membership")
        stmt = (
            select(
                volunteer_application_invites.c.id,
                volunteer_application_invites.c.token,
                volunteer_application_invites.c.email,
                volunteer_application_invites.c.created_at,
                volunteer_application_invites.c.source,
                volunteer_application_invites.c.status,
                volunteer_application_invites.c.initial_group_id,
                volunteer_application_invites.c.initial_role_id,
                volunteer_application_invites.c.first_choice_group_id,
                volunteer_application_invites.c.second_choice_group_id,
                volunteer_application_invites.c.trial_shift_attended,
                volunteer_application_invites.c.full_profile_submitted_at,
                volunteer_application_invites.c.promoted_volunteer_id,
                volunteer_application_invites.c.promoted_at,
                volunteer_application_submissions.c.id.label("pending_volunteer_id"),
                volunteer_application_submissions.c.first_name,
                volunteer_application_submissions.c.last_name,
                volunteer_application_submissions.c.phone,
                volunteer_application_submissions.c.studiested,
                volunteer_application_submissions.c.bakgrunn,
                accepted_group.c.name.label("initial_group_name"),
                accepted_role.c.name.label("initial_role_name"),
                first_choice_group.c.name.label("first_choice_group_name"),
                second_choice_group.c.name.label("second_choice_group_name"),
                group_membership.c.group_id.label("group_id"),
                group_membership.c.role.label("group_role"),
                group_membership.c.status.label("group_status"),
            )
            .select_from(
                volunteer_application_invites.outerjoin(
                    volunteer_application_submissions, volunteer_application_submissions.c.invite_id == volunteer_application_invites.c.id
                )
                .outerjoin(
                    group_membership,
                    group_membership.c.invite_id == volunteer_application_invites.c.id,
                )
                .outerjoin(
                    accepted_group,
                    accepted_group.c.id == volunteer_application_invites.c.initial_group_id,
                )
                .outerjoin(
                    accepted_role, accepted_role.c.id == volunteer_application_invites.c.initial_role_id
                )
                .outerjoin(
                    first_choice_group,
                    first_choice_group.c.id == volunteer_application_invites.c.first_choice_group_id,
                )
                .outerjoin(
                    second_choice_group,
                    second_choice_group.c.id == volunteer_application_invites.c.second_choice_group_id,
                )
            )
            .where(volunteer_application_invites.c.promoted_volunteer_id.is_(None))
            .order_by(volunteer_application_invites.c.created_at.desc(), volunteer_application_invites.c.id.desc())
        )
        session = self.session
        rows = (await session.execute(stmt)).mappings().all()
        group_ids = {row["group_id"] for row in rows if row["group_id"] is not None}
        group_members_by_id = {
            group_id: await self.list_group_members(group_id) for group_id in group_ids
        }
        return [
            VolunteerApplicationListItem(
                registration_id=row["id"],
                token=row["token"],
                email=row["email"],
                created_at=row["created_at"],
                submitted=row["full_profile_submitted_at"] is not None,
                source=row["source"],
                status=row["status"],
                pending_volunteer_id=row["pending_volunteer_id"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                phone=row["phone"],
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
        latest_assignment_rank = (
            func.row_number()
            .over(
                partition_by=role_assignments.c.volunteer_id,
                order_by=(role_assignments.c.id.desc(),),
            )
            .label("assignment_rank")
        )
        latest_assignment_rows = (
            select(
                role_assignments.c.volunteer_id.label("volunteer_id"),
                role_assignments.c.group_id.label("latest_group_id"),
                role_assignments.c.role_id.label("latest_role_id"),
                role_assignments.c.semester.label("latest_semester_code"),
                latest_assignment_rank,
            )
        ).subquery()
        latest_assignment = (
            select(
                latest_assignment_rows.c.volunteer_id,
                latest_assignment_rows.c.latest_group_id,
                latest_assignment_rows.c.latest_role_id,
                latest_assignment_rows.c.latest_semester_code,
            ).where(latest_assignment_rows.c.assignment_rank == 1)
        ).subquery()
        stmt = (
            select(
                volunteer_records.c.id,
                volunteer_records.c.first_name,
                volunteer_records.c.last_name,
                volunteer_records.c.email,
                volunteer_records.c.phone,
                volunteer_records.c.created_at,
                latest_assignment.c.latest_semester_code,
                groups.c.name.label("latest_group_name"),
                assignment_roles.c.name.label("latest_role_name"),
                volunteer_photos.c.sha1.label("photo_sha1"),
                volunteer_photos.c.filetype.label("photo_filetype"),
                volunteer_application_invites.c.id.label("registration_id"),
                volunteer_application_group_members.c.group_id.label("group_id"),
                volunteer_application_group_members.c.role.label("group_role"),
                volunteer_application_group_members.c.status.label("group_status"),
            )
            .select_from(
                volunteer_records.outerjoin(
                    latest_assignment, latest_assignment.c.volunteer_id == volunteer_records.c.id
                )
                .outerjoin(groups, groups.c.id == latest_assignment.c.latest_group_id)
                .outerjoin(assignment_roles, assignment_roles.c.id == latest_assignment.c.latest_role_id)
                .outerjoin(
                    volunteer_photos, volunteer_photos.c.volunteer_id == volunteer_records.c.id
                )
                .outerjoin(
                    volunteer_application_invites, volunteer_application_invites.c.promoted_volunteer_id == volunteer_records.c.id
                )
                .outerjoin(
                    volunteer_application_group_members,
                    volunteer_application_group_members.c.invite_id == volunteer_application_invites.c.id,
                )
            )
            .order_by(volunteer_records.c.id.desc())
            .limit(limit)
        )
        if before_volunteer_id is not None:
            stmt = stmt.where(volunteer_records.c.id < before_volunteer_id)
        session = self.session
        rows = (await session.execute(stmt)).mappings().all()
        return [dict(row) for row in rows]

    async def list_recent_registration_group_members(self, group_id: int) -> list[dict]:
        latest_assignment_rank = (
            func.row_number()
            .over(
                partition_by=role_assignments.c.volunteer_id,
                order_by=(role_assignments.c.id.desc(),),
            )
            .label("assignment_rank")
        )
        latest_assignment_rows = (
            select(
                role_assignments.c.volunteer_id.label("volunteer_id"),
                role_assignments.c.group_id.label("latest_group_id"),
                role_assignments.c.role_id.label("latest_role_id"),
                role_assignments.c.semester.label("latest_semester_code"),
                latest_assignment_rank,
            )
        ).subquery()
        latest_assignment = (
            select(
                latest_assignment_rows.c.volunteer_id,
                latest_assignment_rows.c.latest_group_id,
                latest_assignment_rows.c.latest_role_id,
                latest_assignment_rows.c.latest_semester_code,
            ).where(latest_assignment_rows.c.assignment_rank == 1)
        ).subquery()
        stmt = (
            select(
                volunteer_records.c.id,
                volunteer_records.c.first_name,
                volunteer_records.c.last_name,
                volunteer_records.c.email,
                volunteer_records.c.phone,
                volunteer_records.c.created_at,
                latest_assignment.c.latest_semester_code,
                groups.c.name.label("latest_group_name"),
                assignment_roles.c.name.label("latest_role_name"),
                volunteer_photos.c.sha1.label("photo_sha1"),
                volunteer_photos.c.filetype.label("photo_filetype"),
                volunteer_application_invites.c.id.label("registration_id"),
                volunteer_application_group_members.c.group_id.label("group_id"),
                volunteer_application_group_members.c.role.label("group_role"),
                volunteer_application_group_members.c.status.label("group_status"),
            )
            .select_from(
                volunteer_application_group_members.join(
                    volunteer_application_invites,
                    volunteer_application_invites.c.id == volunteer_application_group_members.c.invite_id,
                )
                .join(volunteer_records, volunteer_records.c.id == volunteer_application_invites.c.promoted_volunteer_id)
                .outerjoin(
                    latest_assignment, latest_assignment.c.volunteer_id == volunteer_records.c.id
                )
                .outerjoin(groups, groups.c.id == latest_assignment.c.latest_group_id)
                .outerjoin(assignment_roles, assignment_roles.c.id == latest_assignment.c.latest_role_id)
                .outerjoin(
                    volunteer_photos, volunteer_photos.c.volunteer_id == volunteer_records.c.id
                )
            )
            .where(volunteer_application_group_members.c.group_id == group_id)
            .order_by(volunteer_application_group_members.c.id.asc())
        )
        session = self.session
        rows = (await session.execute(stmt)).mappings().all()
        return [dict(row) for row in rows]

    async def count_pending_volunteer_applications(self) -> int:
        stmt = (
            select(func.count())
            .select_from(
                volunteer_application_invites.join(
                    volunteer_application_submissions, volunteer_application_submissions.c.invite_id == volunteer_application_invites.c.id
                )
            )
            .where(volunteer_application_invites.c.promoted_volunteer_id.is_(None))
        )
        session = self.session
        count = await session.scalar(stmt)
        return int(count or 0)

    async def get_volunteer_application_detail(
        self, registration_id: int
    ) -> VolunteerApplicationDetail | None:
        return await self._get_detail(
            select(volunteer_application_invites.c.id).where(volunteer_application_invites.c.id == registration_id)
        )

    async def get_volunteer_application_by_token(
        self, token: str
    ) -> VolunteerApplicationDetail | None:
        return await self._get_detail(
            select(volunteer_application_invites.c.id).where(volunteer_application_invites.c.token == token)
        )

    async def find_group_ids_by_names(self, names: list[str]) -> dict[str, int]:
        if not names:
            return {}
        stmt = select(groups.c.id, groups.c.name).where(groups.c.name.in_(names))
        session = self.session
        rows = (await session.execute(stmt)).mappings().all()
        return {row["name"]: row["id"] for row in rows}

    async def save_submission(
        self,
        *,
        registration_id: int,
        email: str,
        submission: VolunteerApplicationSubmissionInput,
        photo_sha1: str | None,
        photo_filetype: str | None,
    ) -> None:
        session = self.session
        registration_row = (
            (
                await session.execute(
                    select(volunteer_application_invites.c.promoted_volunteer_id)
                    .where(volunteer_application_invites.c.id == registration_id)
                    .limit(1)
                )
            )
            .mappings()
            .first()
        )
        if registration_row is None:
            return

        volunteer_id = registration_row["promoted_volunteer_id"]
        if volunteer_id is not None:
            await session.execute(
                update(volunteer_records)
                .where(volunteer_records.c.id == volunteer_id)
                .values(
                    first_name=submission.first_name,
                    last_name=submission.last_name,
                    email=email,
                    gender=submission.gender,
                    birth_date=submission.birth_date,
                    street_address=submission.address,
                    postal_code=submission.postal_code,
                    phone=normalize_phone_number(submission.phone),
                )
            )
            if photo_sha1 and photo_filetype:
                existing_photo = (
                    (
                        await session.execute(
                            select(volunteer_photos.c.volunteer_id)
                            .where(volunteer_photos.c.volunteer_id == volunteer_id)
                            .limit(1)
                        )
                    )
                    .mappings()
                    .first()
                )
                if existing_photo:
                    await session.execute(
                        update(volunteer_photos)
                        .where(volunteer_photos.c.volunteer_id == volunteer_id)
                        .values(sha1=photo_sha1, filetype=photo_filetype)
                    )
                else:
                    await session.execute(
                        insert(volunteer_photos).values(
                            volunteer_id=volunteer_id,
                            sha1=photo_sha1,
                            filetype=photo_filetype,
                        )
                    )
            await session.execute(
                update(volunteer_application_invites)
                .where(volunteer_application_invites.c.id == registration_id)
                .values(full_profile_submitted_at=func.now())
            )
            return

        existing_row = (
            (
                await session.execute(
                    select(
                        volunteer_application_submissions.c.id,
                        volunteer_application_submissions.c.studiested,
                        volunteer_application_submissions.c.bakgrunn,
                    )
                    .where(volunteer_application_submissions.c.invite_id == registration_id)
                    .limit(1)
                )
            )
            .mappings()
            .first()
        )
        payload = {
            "first_name": submission.first_name,
            "last_name": submission.last_name,
            "email": email,
            "gender": submission.gender,
            "birth_date": submission.birth_date,
            "street_address": submission.address,
            "postal_code": submission.postal_code,
            "phone": normalize_phone_number(submission.phone),
            "photo_sha1": photo_sha1,
            "photo_filetype": photo_filetype,
            "studiested": existing_row["studiested"] if existing_row else None,
            "bakgrunn": existing_row["bakgrunn"] if existing_row else None,
        }
        if existing_row:
            await session.execute(
                update(volunteer_application_submissions)
                .where(volunteer_application_submissions.c.invite_id == registration_id)
                .values(**payload)
            )
        else:
            await session.execute(
                insert(volunteer_application_submissions).values(
                    invite_id=registration_id,
                    **payload,
                )
            )
        await session.execute(
            update(volunteer_application_invites)
            .where(volunteer_application_invites.c.id == registration_id)
            .values(status=ApplicationState.SUBMITTED, full_profile_submitted_at=func.now())
        )

    async def set_trial_shift_attended(
        self, registration_id: int, *, attended: bool
    ) -> None:
        session = self.session
        await session.execute(
            update(volunteer_application_invites)
            .where(volunteer_application_invites.c.id == registration_id)
            .values(
                trial_shift_attended=attended,
                trial_shift_marked_at=datetime.now(UTC) if attended else None,
            )
        )

    async def find_volunteer_id_by_email(self, email: str) -> int | None:
        session = self.session
        return await session.scalar(
            select(volunteer_records.c.id)
            .where(func.lower(func.coalesce(volunteer_records.c.email, "")) == email.lower())
            .limit(1)
        )

    async def find_active_registration_id_by_email(self, email: str) -> int | None:
        session = self.session
        return await session.scalar(
            select(volunteer_application_invites.c.id)
            .where(
                func.lower(func.coalesce(volunteer_application_invites.c.email, ""))
                == email.lower(),
                volunteer_application_invites.c.promoted_volunteer_id.is_(None),
                volunteer_application_invites.c.status != ApplicationState.REJECTED,
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
                volunteer_application_group_members.c.group_id,
                volunteer_application_group_members.c.invite_id,
                volunteer_application_group_members.c.applicant_email,
                volunteer_application_group_members.c.role,
                volunteer_application_group_members.c.status,
                volunteer_application_group_members.c.dropped_at,
                volunteer_application_invites.c.full_profile_submitted_at,
                volunteer_application_invites.c.trial_shift_attended,
                volunteer_application_invites.c.promoted_volunteer_id,
                volunteer_application_submissions.c.id.label("pending_volunteer_id"),
                volunteer_application_submissions.c.first_name,
                volunteer_application_submissions.c.last_name,
            )
            .select_from(
                volunteer_application_group_members.outerjoin(
                    volunteer_application_invites,
                    volunteer_application_invites.c.id == volunteer_application_group_members.c.invite_id,
                ).outerjoin(
                    volunteer_application_submissions, volunteer_application_submissions.c.invite_id == volunteer_application_invites.c.id
                )
            )
            .where(volunteer_application_group_members.c.group_id == group_id)
            .order_by(volunteer_application_group_members.c.id.asc())
        )
        if not include_dropped:
            stmt = stmt.where(volunteer_application_group_members.c.status == MembershipState.ACTIVE)
        session = self.session
        rows = (await session.execute(stmt)).mappings().all()
        return [
            VolunteerApplicationGroupMember(
                group_id=row["group_id"],
                registration_id=row["invite_id"],
                email=row["applicant_email"],
                role=row["role"],
                status=row["status"],
                submitted=row["full_profile_submitted_at"] is not None,
                pending_volunteer_id=row["pending_volunteer_id"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                trial_shift_attended=bool(row["trial_shift_attended"]),
                promoted_volunteer_id=row["promoted_volunteer_id"],
                dropped_at=row["dropped_at"],
            )
            for row in rows
        ]

    async def list_group_admin_email_recipients(self, group_id: int) -> list[str]:
        stmt = (
            select(func.lower(user_accounts.c.email).label("email"))
            .select_from(
                group_admin_memberships.join(
                    user_accounts,
                    user_accounts.c.auth_user_id
                    == group_admin_memberships.c.auth_user_id,
                )
            )
            .where(
                group_admin_memberships.c.group_id == group_id,
                user_accounts.c.email.is_not(None),
                user_accounts.c.email != "",
            )
            .distinct()
            .order_by(func.lower(user_accounts.c.email))
        )
        session = self.session
        return [row for row in await session.scalars(stmt)]

    async def approve_volunteer_application(
        self,
        registration: VolunteerApplicationDetail,
        *,
        accepted_group_id: int | None,
    ) -> int:
        session = self.session
        if (
            registration.initial_role_id is not None
            and accepted_group_id is not None
        ):
            role_match = await session.scalar(
                select(
                    exists().where(
                        assignment_roles.c.id == registration.initial_role_id,
                        assignment_roles.c.group_id == accepted_group_id,
                    )
                )
            )
            if not role_match:
                raise VolunteerApplicationConflictError(
                    "The selected initial assignment_roles is no longer valid for the chosen group."
                )
        inserted = (
            (
                await session.execute(
                    insert(volunteer_records)
                    .values(
                        first_name=registration.first_name,
                        last_name=registration.last_name or "",
                        email=registration.email,
                        gender=registration.gender or "A",
                        birth_date=registration.birth_date,
                        street_address=registration.address,
                        postal_code=registration.postal_code,
                        phone=normalize_phone_number(registration.phone),
                    )
                    .returning(volunteer_records.c.id)
                )
            )
            .mappings()
            .one()
        )
        if registration.photo_sha1 and registration.photo_filetype:
            await session.execute(
                insert(volunteer_photos).values(
                    volunteer_id=inserted["id"],
                    sha1=registration.photo_sha1,
                    filetype=registration.photo_filetype,
                )
            )
        if accepted_group_id is not None:
            await session.execute(
                insert(role_assignments).values(
                    volunteer_id=inserted["id"],
                    group_id=accepted_group_id,
                    role_id=registration.initial_role_id,
                    semester=get_current_semester_code(),
                    contract_signed=False,
                )
            )
        await session.execute(
            update(volunteer_application_invites)
            .where(volunteer_application_invites.c.id == registration.registration_id)
            .values(
                promoted_volunteer_id=inserted["id"],
                promoted_at=func.now(),
                status=ApplicationState.PROMOTED,
                initial_group_id=accepted_group_id,
            )
        )
        return inserted["id"]

    async def delete_volunteer_application(self, registration_id: int) -> None:
        session = self.session
        await session.execute(
            delete(volunteer_application_submissions).where(
                volunteer_application_submissions.c.invite_id == registration_id
            )
        )
        await session.execute(
            delete(volunteer_application_invites).where(volunteer_application_invites.c.id == registration_id)
        )

    async def drop_group_invitee(
        self,
        registration_id: int,
        *,
        dropped_by_user_id: int | None = None,
    ) -> None:
        session = self.session
        await session.execute(
            update(volunteer_application_group_members)
            .where(
                volunteer_application_group_members.c.invite_id == registration_id,
                volunteer_application_group_members.c.role == "invitee",
                volunteer_application_group_members.c.status == MembershipState.ACTIVE,
            )
            .values(
                status=MembershipState.DROPPED,
                dropped_at=func.now(),
                dropped_by_user_account_id=dropped_by_user_id,
            )
        )

    async def append_domain_event(
        self, event: DomainEventRecord, *, subject_id: int
    ) -> None:
        """Append one audit row; runs in the ambient request transaction
        so the event commits or rolls back with the state change it records."""
        await self.session.execute(
            insert(domain_events).values(
                event_type=event.event_type,
                actor_user_account_id=event.actor_user_account_id,
                subject_type=event.subject_type,
                subject_id=subject_id,
                payload=event.payload,
                occurred_at=event.occurred_at,
            )
        )

    async def _get_detail(self, id_query) -> VolunteerApplicationDetail | None:
        accepted_group = groups.alias("accepted_group")
        first_choice_group = groups.alias("first_choice_group")
        second_choice_group = groups.alias("second_choice_group")
        accepted_role = assignment_roles.alias("accepted_role")
        group_membership = volunteer_application_group_members.alias("group_membership")
        detail_stmt = (
            select(
                volunteer_application_invites.c.id,
                volunteer_application_invites.c.token,
                volunteer_application_invites.c.email,
                volunteer_application_invites.c.created_at,
                volunteer_application_invites.c.source,
                volunteer_application_invites.c.status,
                volunteer_application_invites.c.initial_group_id,
                volunteer_application_invites.c.initial_role_id,
                volunteer_application_invites.c.first_choice_group_id,
                volunteer_application_invites.c.second_choice_group_id,
                volunteer_application_invites.c.trial_shift_attended,
                volunteer_application_invites.c.trial_shift_marked_at,
                volunteer_application_invites.c.full_profile_submitted_at,
                volunteer_application_invites.c.promoted_volunteer_id,
                volunteer_application_invites.c.promoted_at,
                volunteer_application_submissions.c.id.label("pending_volunteer_id"),
                volunteer_application_submissions.c.first_name,
                volunteer_application_submissions.c.last_name,
                volunteer_application_submissions.c.phone,
                volunteer_application_submissions.c.birth_date,
                volunteer_application_submissions.c.gender,
                volunteer_application_submissions.c.street_address,
                volunteer_application_submissions.c.postal_code,
                volunteer_application_submissions.c.photo_sha1,
                volunteer_application_submissions.c.photo_filetype,
                volunteer_application_submissions.c.studiested,
                volunteer_application_submissions.c.bakgrunn,
                accepted_group.c.name.label("initial_group_name"),
                accepted_role.c.name.label("initial_role_name"),
                first_choice_group.c.name.label("first_choice_group_name"),
                second_choice_group.c.name.label("second_choice_group_name"),
                group_membership.c.group_id.label("group_id"),
                group_membership.c.role.label("group_role"),
                group_membership.c.status.label("group_status"),
            )
            .select_from(
                volunteer_application_invites.outerjoin(
                    volunteer_application_submissions, volunteer_application_submissions.c.invite_id == volunteer_application_invites.c.id
                )
                .outerjoin(
                    group_membership,
                    group_membership.c.invite_id == volunteer_application_invites.c.id,
                )
                .outerjoin(
                    accepted_group,
                    accepted_group.c.id == volunteer_application_invites.c.initial_group_id,
                )
                .outerjoin(
                    accepted_role, accepted_role.c.id == volunteer_application_invites.c.initial_role_id
                )
                .outerjoin(
                    first_choice_group,
                    first_choice_group.c.id == volunteer_application_invites.c.first_choice_group_id,
                )
                .outerjoin(
                    second_choice_group,
                    second_choice_group.c.id == volunteer_application_invites.c.second_choice_group_id,
                )
            )
            .where(volunteer_application_invites.c.id.in_(id_query))
            .limit(1)
        )
        session = self.session
        row = (await session.execute(detail_stmt)).mappings().first()
        if row is None:
            return None
        group_members = (
            await self.list_group_members(row["group_id"])
            if row["group_id"] is not None
            else None
        )
        return VolunteerApplicationDetail(
            registration_id=row["id"],
            token=row["token"],
            email=row["email"],
            created_at=row["created_at"],
            submitted=row["full_profile_submitted_at"] is not None,
            source=row["source"],
            status=row["status"],
            pending_volunteer_id=row["pending_volunteer_id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            phone=row["phone"],
            birth_date=row["birth_date"],
            gender=row["gender"],
            address=row["street_address"],
            postal_code=row["postal_code"],
            photo_sha1=row["photo_sha1"],
            photo_filetype=row["photo_filetype"],
            photo_url=(
                self.media_token_service.build_photo_media_url(
                    f"{row['photo_sha1']}.{row['photo_filetype']}"
                )
                if row["photo_sha1"]
                and row["photo_filetype"]
                and self.media_token_service is not None
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
            (
                await session.execute(
                    select(
                        groups.c.name.label("group_name"),
                        assignment_roles.c.name.label("role_name"),
                    )
                    .select_from(groups.outerjoin(assignment_roles, assignment_roles.c.id == initial_role_id))
                    .where(groups.c.id == initial_group_id)
                    .limit(1)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return {"group_name": None, "role_name": None}
        return {"group_name": row["group_name"], "role_name": row["role_name"]}
