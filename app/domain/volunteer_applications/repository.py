from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import SqlAlchemyRepository
from app.domain.admin_accounts.tables import group_admin_memberships, user_accounts
from app.domain.groups.tables import groups
from app.domain.role_assignments.tables import assignment_roles
from app.domain.volunteer_applications.tables import (
    volunteer_application_group_members,
    volunteer_application_groups,
    volunteer_application_invites,
    volunteer_application_submissions,
)
from app.domain.volunteers.tables import volunteer_photos, volunteer_records
from app.domain.volunteer_applications.state_machine import (
    ApplicationState,
    DomainEventRecord,
    MembershipState,
)
from app.domain.volunteer_applications.tables import domain_events
from app.domain.volunteer_applications.models import (
    PublicProspectGroup,
    PublicProspectRegistrationResult,
    TrialApplicantCardSnapshot,
    VolunteerApplicationDetail,
    VolunteerApplicationFriendInvite,
    VolunteerApplicationGroupMember,
    VolunteerApplicationInvite,
    VolunteerApplicationSubmissionInput,
    VolunteerApplicationStatusEvent,
)
from app.shared.phone_numbers import normalize_phone_number
from app.media_tokens import MediaTokenService
from app.observability import current_trace_id


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
        first_choice_label: str,
        second_choice_label: str | None,
        initial_group_id: int | None,
        initial_role_id: int | None,
        first_choice_group_id: int,
        second_choice_group_id: int | None,
        friend_invites: list[tuple[str, str]] | None = None,
        inviter_name: str | None = None,
        first_choice_group_name: str | None = None,
        origin_trace_id: str | None = None,
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
                        status=ApplicationState.NEW,
                        initial_group_id=initial_group_id,
                        initial_role_id=initial_role_id,
                        first_choice_group_id=first_choice_group_id,
                        second_choice_group_id=second_choice_group_id,
                        first_choice_label=first_choice_label,
                        second_choice_label=second_choice_label,
                        trial_shift_attended=False,
                        origin_trace_id=origin_trace_id,
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
                            status=ApplicationState.NEW,
                            initial_group_id=initial_group_id,
                            initial_role_id=initial_role_id,
                            first_choice_group_id=first_choice_group_id,
                            second_choice_group_id=second_choice_group_id,
                            first_choice_label=first_choice_label,
                            second_choice_label=second_choice_label,
                            trial_shift_attended=False,
                            origin_trace_id=origin_trace_id,
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
        return PublicProspectRegistrationResult(detail=detail, friend_invites=created_friend_invites)

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
                        status=ApplicationState.NEW,
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

    async def count_pending_volunteer_applications(self) -> int:
        stmt = (
            select(func.count())
            .select_from(
                volunteer_application_invites.join(
                    volunteer_application_submissions,
                    volunteer_application_submissions.c.invite_id == volunteer_application_invites.c.id,
                )
            )
            .where(
                volunteer_application_invites.c.status.not_in(
                    [ApplicationState.VOLUNTEER, ApplicationState.NOT_VOLUNTEER]
                )
            )
        )
        session = self.session
        count = await session.scalar(stmt)
        return int(count or 0)

    async def get_volunteer_application_detail(self, registration_id: int) -> VolunteerApplicationDetail | None:
        return await self._get_detail(
            select(volunteer_application_invites.c.id).where(volunteer_application_invites.c.id == registration_id)
        )

    async def get_volunteer_application_by_token(self, token: str) -> VolunteerApplicationDetail | None:
        return await self._get_detail(
            select(volunteer_application_invites.c.id).where(volunteer_application_invites.c.token == token)
        )

    async def find_public_prospect_groups_by_slugs(self, slugs: list[str]) -> dict[str, PublicProspectGroup]:
        if not slugs:
            return {}
        stmt = select(groups.c.id, groups.c.slug, groups.c.name).where(groups.c.slug.in_(slugs))
        session = self.session
        rows = (await session.execute(stmt)).mappings().all()
        return {
            row["slug"]: PublicProspectGroup(
                group_id=row["id"],
                slug=row["slug"],
                name=row["name"],
            )
            for row in rows
        }

    async def find_public_prospect_role_id(self, *, group_id: int, role_name: str) -> int | None:
        return await self.session.scalar(
            select(assignment_roles.c.id)
            .where(
                assignment_roles.c.group_id == group_id,
                assignment_roles.c.name == role_name,
            )
            .limit(1)
        )

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
            .values(full_profile_submitted_at=func.now())
        )

    async def set_application_status(
        self,
        registration_id: int,
        *,
        status: ApplicationState,
        start_trial: bool = False,
    ) -> None:
        values: dict[str, object] = {"status": status}
        if start_trial:
            started_at = datetime.now(UTC)
            values.update(
                trial_started_at=started_at,
                trial_ends_at=started_at + timedelta(days=30),
            )
        await self.session.execute(
            update(volunteer_application_invites)
            .where(volunteer_application_invites.c.id == registration_id)
            .values(**values)
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
                func.lower(func.coalesce(volunteer_application_invites.c.email, "")) == email.lower(),
                volunteer_application_invites.c.status != ApplicationState.VOLUNTEER,
                volunteer_application_invites.c.status != ApplicationState.NOT_VOLUNTEER,
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
                volunteer_application_invites.c.status.label("application_status"),
                volunteer_application_submissions.c.id.label("pending_volunteer_id"),
                volunteer_application_submissions.c.first_name,
                volunteer_application_submissions.c.last_name,
            )
            .select_from(
                volunteer_application_group_members.outerjoin(
                    volunteer_application_invites,
                    volunteer_application_invites.c.id == volunteer_application_group_members.c.invite_id,
                ).outerjoin(
                    volunteer_application_submissions,
                    volunteer_application_submissions.c.invite_id == volunteer_application_invites.c.id,
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
                application_status=row["application_status"],
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
                    user_accounts.c.auth_user_id == group_admin_memberships.c.auth_user_id,
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

    async def role_matches_group(self, *, role_id: int, group_id: int) -> bool:
        return bool(
            await self.fetch_scalar(
                select(
                    exists().where(
                        assignment_roles.c.id == role_id,
                        assignment_roles.c.group_id == group_id,
                    )
                )
            )
        )

    async def mark_promoted(
        self,
        *,
        registration_id: int,
        volunteer_id: int,
        accepted_group_id: int,
    ) -> None:
        await self.execute(
            update(volunteer_application_invites)
            .where(volunteer_application_invites.c.id == registration_id)
            .values(
                promoted_volunteer_id=volunteer_id,
                promoted_at=func.now(),
                status=ApplicationState.VOLUNTEER,
                initial_group_id=accepted_group_id,
            )
        )

    async def find_active_trial_applicant_by_email(
        self, email: str
    ) -> TrialApplicantCardSnapshot | None:
        return await self._find_active_trial_applicant(email=email)

    async def get_active_trial_applicant(
        self, application_id: int
    ) -> TrialApplicantCardSnapshot | None:
        return await self._find_active_trial_applicant(application_id=application_id)

    async def _find_active_trial_applicant(
        self,
        *,
        email: str | None = None,
        application_id: int | None = None,
    ) -> TrialApplicantCardSnapshot | None:
        accepted_group = groups.alias("trial_group")
        accepted_role = assignment_roles.alias("trial_role")
        stmt = (
            select(
                volunteer_application_invites.c.id,
                volunteer_application_invites.c.created_at,
                volunteer_application_invites.c.trial_ends_at,
                volunteer_application_submissions.c.first_name,
                volunteer_application_submissions.c.last_name,
                volunteer_application_submissions.c.birth_date,
                volunteer_application_submissions.c.photo_sha1,
                volunteer_application_submissions.c.photo_filetype,
                accepted_group.c.name.label("group_name"),
                accepted_group.c.discount_tier,
                accepted_role.c.name.label("role_name"),
            )
            .select_from(
                volunteer_application_invites.join(
                    volunteer_application_submissions,
                    volunteer_application_submissions.c.invite_id
                    == volunteer_application_invites.c.id,
                )
                .outerjoin(
                    accepted_group,
                    accepted_group.c.id
                    == func.coalesce(
                        volunteer_application_invites.c.initial_group_id,
                        volunteer_application_invites.c.first_choice_group_id,
                    ),
                )
                .outerjoin(
                    accepted_role,
                    accepted_role.c.id
                    == volunteer_application_invites.c.initial_role_id,
                )
            )
            .where(
                volunteer_application_invites.c.status == ApplicationState.TRIAL,
                volunteer_application_invites.c.trial_ends_at > func.now(),
                volunteer_application_invites.c.full_profile_submitted_at.is_not(None),
                volunteer_application_submissions.c.photo_sha1.is_not(None),
                volunteer_application_submissions.c.photo_filetype.is_not(None),
            )
            .limit(1)
        )
        if email is not None:
            stmt = stmt.where(
                func.lower(volunteer_application_invites.c.email) == email.lower()
            )
        if application_id is not None:
            stmt = stmt.where(volunteer_application_invites.c.id == application_id)
        row = await self.fetch_first_mapping(stmt)
        if row is None:
            return None
        return TrialApplicantCardSnapshot(
            application_id=row["id"],
            first_name=row["first_name"] or "",
            last_name=row["last_name"],
            birth_date=row["birth_date"],
            created_at=row["created_at"],
            trial_ends_at=row["trial_ends_at"],
            photo_path=f"{row['photo_sha1']}.{row['photo_filetype']}",
            group_name=row["group_name"] or "Kvarteret",
            role_name=row["role_name"] or "Prøvefrivillig",
            discount_level=row["discount_tier"],
        )

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

    async def append_domain_event(self, event: DomainEventRecord, *, subject_id: int) -> int:
        """Append one audit row; runs in the ambient request transaction
        so the event commits or rolls back with the state change it records."""
        result = await self.session.execute(
            insert(domain_events)
            .values(
                event_type=event.event_type,
                actor_user_account_id=event.actor_user_account_id,
                subject_type=event.subject_type,
                subject_id=subject_id,
                payload=event.payload,
                occurred_at=event.occurred_at,
                trace_id=event.trace_id or current_trace_id(),
            )
            .returning(domain_events.c.id)
        )
        return int(result.scalar_one())

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
                volunteer_application_invites.c.trial_started_at,
                volunteer_application_invites.c.trial_ends_at,
                volunteer_application_invites.c.full_profile_submitted_at,
                volunteer_application_invites.c.promoted_volunteer_id,
                volunteer_application_invites.c.promoted_at,
                volunteer_application_invites.c.origin_trace_id,
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
                func.coalesce(
                    volunteer_application_invites.c.first_choice_label,
                    first_choice_group.c.name,
                ).label("first_choice_group_name"),
                func.coalesce(
                    volunteer_application_invites.c.second_choice_label,
                    second_choice_group.c.name,
                ).label("second_choice_group_name"),
                group_membership.c.group_id.label("group_id"),
                group_membership.c.role.label("group_role"),
                group_membership.c.status.label("group_status"),
            )
            .select_from(
                volunteer_application_invites.outerjoin(
                    volunteer_application_submissions,
                    volunteer_application_submissions.c.invite_id == volunteer_application_invites.c.id,
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
                    accepted_role,
                    accepted_role.c.id == volunteer_application_invites.c.initial_role_id,
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
        group_members = await self.list_group_members(row["group_id"]) if row["group_id"] is not None else None
        status_history = await self.list_status_history(row["id"])
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
            trial_started_at=row["trial_started_at"],
            trial_ends_at=row["trial_ends_at"],
            promoted_volunteer_id=row["promoted_volunteer_id"],
            promoted_at=row["promoted_at"],
            group_id=row["group_id"],
            group_role=row["group_role"],
            group_status=row["group_status"],
            group_members=group_members,
            status_history=status_history,
            origin_trace_id=row["origin_trace_id"],
        )

    async def list_status_history(
        self, registration_id: int
    ) -> list[VolunteerApplicationStatusEvent]:
        event_statuses = {
            "prospect_registered": ApplicationState.NEW.value,
            "application_invited": ApplicationState.NEW.value,
            "application_contacted": ApplicationState.CONTACTED.value,
            "trial_started": ApplicationState.TRIAL.value,
            "application_approved": ApplicationState.VOLUNTEER.value,
            "application_rejected": ApplicationState.NOT_VOLUNTEER.value,
            "application_reopened": ApplicationState.CONTACTED.value,
            "application_volunteer_restored": ApplicationState.VOLUNTEER.value,
        }
        actor = user_accounts.alias("event_actor")
        rows = await self.fetch_all_mappings(
            select(
                domain_events.c.event_type,
                domain_events.c.actor_user_account_id,
                domain_events.c.occurred_at,
                actor.c.display_name,
                actor.c.username,
            )
            .select_from(
                domain_events.outerjoin(
                    actor, actor.c.id == domain_events.c.actor_user_account_id
                )
            )
            .where(
                domain_events.c.subject_type == "application",
                domain_events.c.subject_id == registration_id,
                domain_events.c.event_type.in_(tuple(event_statuses)),
            )
            .order_by(domain_events.c.occurred_at.desc(), domain_events.c.id.desc())
        )
        return [
            VolunteerApplicationStatusEvent(
                event_type=row["event_type"],
                status=event_statuses[row["event_type"]],
                actor_display_name=row["display_name"] or row["username"],
                actor_user_account_id=row["actor_user_account_id"],
                occurred_at=row["occurred_at"],
            )
            for row in rows
        ]

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
