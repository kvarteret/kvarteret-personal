from __future__ import annotations

import logging
import re
from asyncio import to_thread
from secrets import token_hex, token_urlsafe

from app.config import Settings
from app.db.session import commit_request_session
from app.errors import NotConfiguredError
from app.infrastructure.email.applicant_templates import (
    ApplicantEmailTemplateRenderer,
    ApplicantEmailTemplateRendererProtocol,
)
from app.infrastructure.email.protocols import EmailSenderProtocol
from app.infrastructure.media.protocols import PhotoProcessorProtocol
from app.shared.phone_numbers import normalize_phone_number, normalize_required_phone_number
from app.infrastructure.storage.protocols import StorageProtocol
from app.domain.volunteer_applications.side_effects import (
    VolunteerApplicationSideEffects,
)
from app.domain.volunteer_applications.state_machine import (
    DomainEventRecord,
    IllegalTransition,
    MembershipState,
)
from app.domain.volunteer_applications.models import (
    ActiveVolunteerRegistrationExistsError,
    PublicProspectRegistrationInput,
    PublicProspectRegistrationResult,
    VolunteerAlreadyExistsError,
    VolunteerApplicationConflictError,
    VolunteerApplicationDetail,
    VolunteerApplicationFieldConflictError,
    VolunteerApplicationFieldValidationError,
    VolunteerApplicationGroupMember,
    VolunteerApplicationInvite,
    VolunteerApplicationNotFoundError,
    VolunteerApplicationValidationError,
    VolunteerApplicationsRepositoryProtocol,
    VolunteerCreatorProtocol,
    VolunteerApplicationSubmissionInput,
    build_full_name as _build_full_name,
)
from app.domain.volunteer_applications.queries import VolunteerApplicationsQueries
from app.domain.volunteer_applications.workflow import VolunteerApplicationWorkflow

_REGISTRATION_NOT_FOUND = "Registration was not found."


def _normalize_phone(phone: str) -> str:
    try:
        return normalize_required_phone_number(phone)
    except ValueError as exc:
        raise VolunteerApplicationValidationError(str(exc)) from exc


def _check_postal_code(postal_code: str | None) -> None:
    if postal_code is not None and not re.fullmatch(r"\d{4}", postal_code):
        raise VolunteerApplicationValidationError(
            "Postal code must be exactly 4 digits (e.g. 5011)."
        )

PUBLIC_PROSPECT_GROUPS = {
    "skjenkegruppen": "Skjenkegruppen",
    "kraft": "Kraftetaten",
    "vaktetaten": "Vaktetaten",
}

logger = logging.getLogger(__name__)


class VolunteerApplicationsService(VolunteerApplicationsQueries):
    def __init__(
        self,
        settings: Settings,
        repository: VolunteerApplicationsRepositoryProtocol,
        email_sender: EmailSenderProtocol,
        volunteer_creator: VolunteerCreatorProtocol,
        applicant_email_renderer: ApplicantEmailTemplateRendererProtocol | None = None,
        storage_service: StorageProtocol | None = None,
        photo_processor: PhotoProcessorProtocol | None = None,
        pending_count_cache_ttl_seconds: int = 30,
    ) -> None:
        super().__init__(
            repository=repository,
            pending_count_cache_ttl_seconds=pending_count_cache_ttl_seconds,
        )
        self.settings = settings
        self.volunteer_creator = volunteer_creator
        self.email_sender = email_sender
        self.applicant_email_renderer = applicant_email_renderer or ApplicantEmailTemplateRenderer()
        self.storage_service = storage_service
        self.photo_processor = photo_processor
        self.workflow = VolunteerApplicationWorkflow(
            operations=self,
            side_effects=VolunteerApplicationSideEffects(
                invalidate_pending_count_cache=self._invalidate_pending_count_cache,
                send_invitation_email=self._send_invitation_email,
                send_friend_invitation_email=self._send_friend_invitation_email,
                send_profile_completion_email=self._send_profile_completion_email,
                storage_service=storage_service,
            ),
        )

    async def create_public_prospect_registration(
        self,
        registration: PublicProspectRegistrationInput,
        *,
        base_url: str | None = None,
    ) -> VolunteerApplicationDetail:
        return await self.workflow.register_public_prospect(
            registration, base_url=base_url
        )

    async def create_public_prospect_registration_record(
        self,
        registration: PublicProspectRegistrationInput,
        *,
        base_url: str | None = None,
    ) -> PublicProspectRegistrationResult:
        normalized_email = registration.email.strip().lower()
        if not normalized_email:
            raise VolunteerApplicationValidationError("E-postadresse er påkrevd.")
        duplicate_volunteer = await self.repository.find_volunteer_id_by_email(normalized_email)
        if duplicate_volunteer is not None:
            raise VolunteerAlreadyExistsError(duplicate_volunteer, normalized_email)
        duplicate_registration = await self.repository.find_active_registration_id_by_email(normalized_email)
        if duplicate_registration is not None:
            raise ActiveVolunteerRegistrationExistsError(duplicate_registration, normalized_email)

        first_choice_slug = registration.first_choice_group_slug.strip().lower()
        second_choice_slug = (registration.second_choice_group_slug or "").strip().lower()
        if not first_choice_slug:
            raise VolunteerApplicationValidationError("Velg et førstevalg.")
        if second_choice_slug and first_choice_slug == second_choice_slug:
            raise VolunteerApplicationValidationError("Førstevalg og andrevalg må være ulike groups.")

        known_choice_names = {
            slug: PUBLIC_PROSPECT_GROUPS[slug]
            for slug in [first_choice_slug, second_choice_slug]
            if slug
            if slug in PUBLIC_PROSPECT_GROUPS
        }
        expected_choice_count = 1 + (1 if second_choice_slug else 0)
        if len(known_choice_names) != expected_choice_count:
            raise VolunteerApplicationValidationError("Én eller flere valgte groups støttes ikke i denne lanseringen.")

        group_ids_by_name = await self.repository.find_group_ids_by_names(list(known_choice_names.values()))
        if len(group_ids_by_name) != expected_choice_count:
            raise VolunteerApplicationConflictError("Én eller flere valgte groups finnes ikke i personaldatabasen.")

        first_name, last_name = _split_full_name(registration.full_name)
        friend_emails = self._normalize_friend_emails(
            registration.friend_emails,
            inviter_email=normalized_email,
        )
        await self._assert_friend_emails_available(friend_emails)

        token = token_urlsafe(24)
        result = await self.repository.create_public_prospect_registration(
            token=token,
            email=normalized_email,
            first_name=first_name,
            last_name=last_name,
            phone=normalize_phone_number(registration.phone),
            study_institution=_normalize_optional_text(registration.study_institution),
            background_details=_normalize_optional_text(registration.background_details),
            first_choice_group_id=group_ids_by_name[known_choice_names[first_choice_slug]],
            second_choice_group_id=(
                group_ids_by_name[known_choice_names[second_choice_slug]]
                if second_choice_slug
                else None
            ),
            friend_invites=[(friend_email, token_urlsafe(24)) for friend_email in friend_emails],
            inviter_name=_build_full_name(first_name, last_name),
            first_choice_group_name=known_choice_names[first_choice_slug],
        )
        return result

    async def create_volunteer_application_invitation(
        self,
        email: str,
        *,
        base_url: str | None = None,
        initial_group_id: int | None = None,
        initial_role_id: int | None = None,
        actor_user_account_id: int | None = None,
    ) -> VolunteerApplicationInvite:
        return await self.workflow.invite(
            email,
            base_url=base_url,
            initial_group_id=initial_group_id,
            initial_role_id=initial_role_id,
            actor_user_account_id=actor_user_account_id,
        )

    async def create_invitation_record(
        self,
        email: str,
        *,
        initial_group_id: int | None = None,
        initial_role_id: int | None = None,
    ) -> VolunteerApplicationInvite:
        normalized_email = email.strip().lower()
        if not normalized_email:
            raise VolunteerApplicationConflictError("An email address is required.")
        if (initial_group_id is None) != (initial_role_id is None):
            raise VolunteerApplicationConflictError("Choose both group and assignment_roles, or leave both empty.")
        duplicate_volunteer = await self.repository.find_volunteer_id_by_email(normalized_email)
        if duplicate_volunteer is not None:
            raise VolunteerAlreadyExistsError(duplicate_volunteer, normalized_email)
        token = token_urlsafe(24)
        invite = await self.repository.create_volunteer_application_invitation(
            email=normalized_email,
            token=token,
            initial_group_id=initial_group_id,
            initial_role_id=initial_role_id,
        )
        return invite

    async def get_volunteer_application_detail(self, registration_id: int) -> VolunteerApplicationDetail | None:
        return await self.repository.get_volunteer_application_detail(registration_id)

    async def get_volunteer_application_by_token(self, token: str) -> VolunteerApplicationDetail | None:
        return await self.repository.get_volunteer_application_by_token(token)

    async def submit_volunteer_application(
        self,
        token: str,
        submission: VolunteerApplicationSubmissionInput,
        *,
        base_url: str | None = None,
        photo_filename: str | None = None,
        photo_content: bytes | None = None,
        photo_content_type: str | None = None,
    ) -> VolunteerApplicationDetail:
        try:
            return await self.workflow.submit(
                token,
                submission,
                base_url=base_url,
                photo_filename=photo_filename,
                photo_content=photo_content,
                photo_content_type=photo_content_type,
            )
        except IllegalTransition as exc:
            raise VolunteerApplicationConflictError(str(exc)) from exc

    async def submit_application_record(
        self,
        token: str,
        submission: VolunteerApplicationSubmissionInput,
        *,
        base_url: str | None = None,
        photo_filename: str | None = None,
        photo_content: bytes | None = None,
        photo_content_type: str | None = None,
    ) -> VolunteerApplicationDetail:
        existing = await self.get_volunteer_application_by_token(token)
        if existing is None:
            raise VolunteerApplicationNotFoundError("Registration token was not found.")

        submission.phone = _normalize_phone(submission.phone)
        _check_postal_code(submission.postal_code)

        # --- Photo handling ---
        has_existing_photo = existing.photo_sha1 is not None
        has_new_photo = bool(photo_filename and photo_content)
        missing_required_photo = not has_existing_photo and not has_new_photo
        if missing_required_photo:
            raise VolunteerApplicationValidationError("Profilbilde er påkrevd.")

        photo_sha1 = existing.photo_sha1
        photo_filetype = existing.photo_filetype
        old_storage_path = _build_photo_storage_path(existing.photo_sha1, existing.photo_filetype)
        new_storage_path = old_storage_path
        uploaded_new_photo = False
        storage_service: StorageProtocol | None = None

        if has_new_photo:
            photo_sha1, photo_filetype, new_storage_path, storage_service = await self._upload_new_photo(
                photo_filename, photo_content
            )
            assert new_storage_path is not None
            uploaded_new_photo = True

        # --- Save and cleanup ---
        await self._save_and_cleanup_photos(
            existing=existing,
            submission=submission,
            photo_sha1=photo_sha1,
            photo_filetype=photo_filetype,
            old_storage_path=old_storage_path,
            new_storage_path=new_storage_path,
            uploaded_new_photo=uploaded_new_photo,
            storage_service=storage_service,
        )

        detail = await self.get_volunteer_application_by_token(token)
        if detail is None:
            raise VolunteerApplicationNotFoundError("Registration token was not found.")

        return detail

    async def _upload_new_photo(
        self, photo_filename: str, photo_content: bytes
    ) -> tuple[str, str, str, StorageProtocol]:
        safe_filename = _sanitize_filename(photo_filename)
        extension = _normalize_extension(safe_filename)
        if extension not in {"jpg", "jpeg", "png", "webp"}:
            raise VolunteerApplicationConflictError(
                "Photos must be jpg, jpeg, png, or webp."
            )
        storage_service = self._require_storage_service()
        photo_sha1 = token_hex(20)
        processed = self._require_photo_processor()(
            photo_content,
            max_upload_bytes=self.settings.photo_upload_max_bytes,
            max_dimension=self.settings.photo_max_dimension,
        )
        new_path = _build_photo_storage_path(photo_sha1, processed.extension)
        await to_thread(
            storage_service.upload_photo,
            new_path,
            processed.content,
            processed.content_type,
        )
        return photo_sha1, processed.extension, new_path, storage_service

    async def _save_and_cleanup_photos(
        self,
        *,
        existing: VolunteerApplicationDetail,
        submission: VolunteerApplicationSubmissionInput,
        photo_sha1: str | None,
        photo_filetype: str | None,
        old_storage_path: str | None,
        new_storage_path: str | None,
        uploaded_new_photo: bool,
        storage_service: StorageProtocol | None,
    ) -> None:
        try:
            await self.repository.save_submission(
                registration_id=existing.registration_id,
                email=existing.email,
                submission=submission,
                photo_sha1=photo_sha1,
                photo_filetype=photo_filetype,
            )
        except Exception:
            should_rollback = (
                uploaded_new_photo
                and storage_service is not None
                and new_storage_path is not None
                and new_storage_path != old_storage_path
            )
            if should_rollback:
                try:
                    await to_thread(
                        storage_service.remove_photo, new_storage_path
                    )
                except Exception:
                    pass
            raise

        should_remove_old = (
            uploaded_new_photo
            and old_storage_path is not None
            and old_storage_path != new_storage_path
        )
        if should_remove_old:
            try:
                await to_thread(
                    self._require_storage_service().remove_photo,
                    old_storage_path,
                )
            except Exception:
                pass

    async def mark_trial_shift_attended(
        self,
        registration_id: int,
        *,
        attended: bool,
        actor_user_account_id: int | None = None,
    ) -> VolunteerApplicationDetail:
        try:
            return await self.workflow.mark_trial_shift_attended(
                registration_id,
                attended=attended,
                actor_user_account_id=actor_user_account_id,
            )
        except IllegalTransition as exc:
            raise VolunteerApplicationConflictError(str(exc)) from exc

    async def mark_trial_shift_attended_record(
        self,
        registration_id: int,
        *,
        attended: bool,
    ) -> VolunteerApplicationDetail:
        detail = await self.get_volunteer_application_detail(registration_id)
        if detail is None:
            raise VolunteerApplicationNotFoundError(_REGISTRATION_NOT_FOUND)
        await self.repository.set_trial_shift_attended(registration_id, attended=attended)
        refreshed = await self.get_volunteer_application_detail(registration_id)
        if refreshed is None:
            raise VolunteerApplicationNotFoundError(_REGISTRATION_NOT_FOUND)
        return refreshed

    async def approve_volunteer_application(
        self,
        registration_id: int,
        *,
        accepted_group_id: int | None = None,
        base_url: str | None = None,
        actor_user_account_id: int | None = None,
    ) -> int:
        try:
            return await self.workflow.approve(
                registration_id,
                accepted_group_id=accepted_group_id,
                base_url=base_url,
                actor_user_account_id=actor_user_account_id,
            )
        except IllegalTransition as exc:
            raise VolunteerApplicationConflictError(str(exc)) from exc

    async def approve_application_record(
        self,
        registration_id: int,
        *,
        accepted_group_id: int | None = None,
    ) -> tuple[VolunteerApplicationDetail, int]:
        detail = await self.get_volunteer_application_detail(registration_id)
        if detail is None:
            raise VolunteerApplicationNotFoundError(_REGISTRATION_NOT_FOUND)
        if detail.pending_volunteer_id is None:
            raise VolunteerApplicationConflictError("Registration is missing prospect details.")
        if detail.promoted_volunteer_id is not None:
            raise VolunteerApplicationConflictError("Registration has already been promoted.")
        self._ensure_group_members_ready_for_promotion(detail)
        duplicate_volunteer = await self.repository.find_volunteer_id_by_email(detail.email)
        if duplicate_volunteer is not None:
            raise VolunteerAlreadyExistsError(duplicate_volunteer, detail.email)
        resolved_group_id = accepted_group_id or detail.initial_group_id or detail.first_choice_group_id
        allowed_group_ids = {
            group_id
            for group_id in [detail.initial_group_id, detail.first_choice_group_id, detail.second_choice_group_id]
            if group_id is not None
        }
        if resolved_group_id is None:
            raise VolunteerApplicationConflictError("Choose a group before promoting this prospect.")
        if allowed_group_ids and resolved_group_id not in allowed_group_ids:
            raise VolunteerApplicationConflictError("The chosen group is not one of the registered committee choices.")
        if detail.initial_role_id is not None and not (
            await self.repository.role_matches_group(
                role_id=detail.initial_role_id, group_id=resolved_group_id
            )
        ):
            raise VolunteerApplicationConflictError(
                "The selected initial assignment_roles is no longer valid for the chosen group."
            )
        # The volunteers module owns onboarding; this module only flips
        # its own invite row once the owning service reports the new id.
        volunteer_id = await self.volunteer_creator.create_from_application(
            first_name=detail.first_name,
            last_name=detail.last_name or "",
            email=detail.email,
            gender=detail.gender or "A",
            birth_date=detail.birth_date,
            street_address=detail.address,
            postal_code=detail.postal_code,
            phone=normalize_phone_number(detail.phone),
            photo_sha1=detail.photo_sha1,
            photo_filetype=detail.photo_filetype,
            group_id=resolved_group_id,
            role_id=detail.initial_role_id,
        )
        await self.repository.mark_promoted(
            registration_id=detail.registration_id,
            volunteer_id=volunteer_id,
            accepted_group_id=resolved_group_id,
        )
        return detail, volunteer_id

    async def approve_volunteer_application_group(
        self,
        group_id: int,
        *,
        accepted_group_id: int,
        base_url: str | None = None,
        actor_user_account_id: int | None = None,
    ) -> list[int]:
        members = await self.repository.list_group_members(group_id, include_dropped=False)
        active_registration_ids = [
            member.registration_id
            for member in members
            if member.registration_id is not None and member.active
        ]
        if not active_registration_ids:
            raise VolunteerApplicationNotFoundError("Group registration was not found.")
        if any(not member.submitted for member in members if member.active):
            raise VolunteerApplicationConflictError(
                "Kan ikke godkjenne før alle gruppemedlemmer har sendt inn sin søknad."
            )
        try:
            return await self.workflow.approve_group(
                active_registration_ids,
                accepted_group_id=accepted_group_id,
                base_url=base_url,
                actor_user_account_id=actor_user_account_id,
            )
        except IllegalTransition as exc:
            raise VolunteerApplicationConflictError(str(exc)) from exc

    async def drop_group_invitee(
        self,
        registration_id: int,
        *,
        dropped_by_user_id: int | None = None,
    ) -> None:
        try:
            await self.workflow.drop_group_invitee(
                registration_id, dropped_by_user_id=dropped_by_user_id
            )
        except IllegalTransition as exc:
            raise VolunteerApplicationConflictError(str(exc)) from exc

    async def drop_group_invitee_record(
        self,
        registration_id: int,
        *,
        dropped_by_user_id: int | None = None,
    ) -> VolunteerApplicationDetail:
        detail = await self.get_volunteer_application_detail(registration_id)
        if detail is None:
            raise VolunteerApplicationNotFoundError(_REGISTRATION_NOT_FOUND)
        if detail.group_role != "invitee" or detail.group_status != MembershipState.ACTIVE:
            raise VolunteerApplicationConflictError("Only active group invitees can be removed from a group.")
        await self.repository.drop_group_invitee(registration_id, dropped_by_user_id=dropped_by_user_id)
        return detail

    async def delete_volunteer_application(
        self,
        registration_id: int,
        *,
        actor_user_account_id: int | None = None,
    ) -> None:
        try:
            await self.workflow.delete(
                registration_id, actor_user_account_id=actor_user_account_id
            )
        except IllegalTransition as exc:
            raise VolunteerApplicationConflictError(str(exc)) from exc

    async def delete_application_record(
        self, registration_id: int
    ) -> VolunteerApplicationDetail:
        detail = await self.get_volunteer_application_detail(registration_id)
        if detail is None:
            raise VolunteerApplicationNotFoundError(_REGISTRATION_NOT_FOUND)
        await self.repository.delete_volunteer_application(registration_id)
        return detail

    async def resend_volunteer_application_invitation(
        self,
        registration_id: int,
        *,
        base_url: str | None = None,
        actor_user_account_id: int | None = None,
    ) -> VolunteerApplicationDetail:
        try:
            return await self.workflow.resend_invitation(
                registration_id,
                base_url=base_url,
                actor_user_account_id=actor_user_account_id,
            )
        except IllegalTransition as exc:
            raise VolunteerApplicationConflictError(str(exc)) from exc

    async def resend_invitation_record(
        self,
        registration_id: int,
    ) -> VolunteerApplicationDetail:
        detail = await self.get_volunteer_application_detail(registration_id)
        if detail is None:
            raise VolunteerApplicationNotFoundError(_REGISTRATION_NOT_FOUND)
        return detail

    async def list_active_group_members(
        self, group_id: int
    ) -> list[VolunteerApplicationGroupMember]:
        return await self.repository.list_group_members(group_id, include_dropped=False)

    async def append_domain_event(
        self, event: DomainEventRecord, *, subject_id: int
    ) -> None:
        await self.repository.append_domain_event(event, subject_id=subject_id)

    def _normalize_friend_emails(
        self,
        friend_emails: list[str] | None,
        *,
        inviter_email: str,
    ) -> list[str]:
        normalized = [email.strip().lower() for email in friend_emails or [] if email and email.strip()]
        if len(normalized) > 2:
            raise VolunteerApplicationFieldValidationError(
                "Du kan legge til maks to venner.",
                {"friendEmails": "Du kan legge til maks to venner."},
            )
        seen: set[str] = {inviter_email}
        field_errors: dict[str, str] = {}
        for index, email in enumerate(normalized):
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                field_errors[str(index)] = "Skriv inn en gyldig e-postadresse."
            elif email in seen:
                field_errors[str(index)] = "E-postadressene må være ulike."
            seen.add(email)
        if field_errors:
            raise VolunteerApplicationFieldValidationError(
                "Én eller flere venneadresser er ugyldige.",
                {"friendEmails": field_errors},
            )
        return normalized

    async def _assert_friend_emails_available(self, friend_emails: list[str]) -> None:
        for index, friend_email in enumerate(friend_emails):
            is_already_volunteer = (
                await self.repository.find_volunteer_id_by_email(friend_email)
            ) is not None
            if is_already_volunteer:
                raise VolunteerApplicationFieldConflictError(
                    "Én av vennene er allerede frivillig.",
                    {"friendEmails": {str(index): "Denne e-postadressen tilhører allerede en frivillig."}},
                )
            has_active_registration = (
                await self.repository.find_active_registration_id_by_email(friend_email)
            ) is not None
            if has_active_registration:
                raise VolunteerApplicationFieldConflictError(
                    "Én av vennene har allerede en is_active søknad.",
                    {"friendEmails": {str(index): "Denne e-postadressen har allerede en is_active søknad."}},
                )

    def _ensure_group_members_ready_for_promotion(self, detail: VolunteerApplicationDetail) -> None:
        if not detail.group_id or detail.group_status != MembershipState.ACTIVE:
            return
        for member in detail.group_members or []:
            if member.registration_id == detail.registration_id or not member.active:
                continue
            if not member.submitted:
                raise VolunteerApplicationConflictError(
                    "Kan ikke godkjenne før alle gruppemedlemmer har sendt inn sin søknad."
                )

    def _require_photo_processor(self) -> PhotoProcessorProtocol:
        if self.photo_processor is None:
            raise NotConfiguredError("Photo processing is not configured yet.")
        return self.photo_processor

    def _require_storage_service(self) -> StorageProtocol:
        if self.storage_service is None:
            raise NotConfiguredError("Supabase credentials are required for storage integration.")
        return self.storage_service

    async def _send_invitation_email(self, *, email: str, token: str, base_url: str | None = None) -> None:
        resolved_base_url = (base_url or self.settings.app_public_base_url or "").rstrip("/")
        if not resolved_base_url:
            raise NotConfiguredError("APP_PUBLIC_BASE_URL is required to send registration invitation emails.")
        invitation_url = f"{resolved_base_url}/apply/{token}"
        rendered_email = self.applicant_email_renderer.render_invitation_email(invitation_url=invitation_url)
        await commit_request_session()
        await self.email_sender.send_email(
            recipient_email=email,
            subject=rendered_email.subject,
            html_body=rendered_email.html_body,
        )

    async def _send_friend_invitation_email(
        self,
        *,
        email: str,
        token: str,
        inviter_name: str,
        first_choice_group_name: str,
        base_url: str | None = None,
    ) -> None:
        resolved_base_url = (base_url or self.settings.app_public_base_url or "").rstrip("/")
        if not resolved_base_url:
            raise NotConfiguredError("APP_PUBLIC_BASE_URL is required to send registration invitation emails.")
        invitation_url = f"{resolved_base_url}/apply/{token}"
        rendered_email = self.applicant_email_renderer.render_friend_invitation_email(
            invitation_url=invitation_url,
            inviter_name=inviter_name,
            first_choice_group_name=first_choice_group_name,
        )
        await commit_request_session()
        await self.email_sender.send_email(
            recipient_email=email,
            subject=rendered_email.subject,
            html_body=rendered_email.html_body,
        )

    async def _send_profile_completion_email(self, *, email: str, token: str, base_url: str | None = None) -> None:
        resolved_base_url = (base_url or self.settings.app_public_base_url or "").rstrip("/")
        if not resolved_base_url:
            raise NotConfiguredError("APP_PUBLIC_BASE_URL is required to send profile completion emails.")
        invitation_url = f"{resolved_base_url}/apply/{token}"
        rendered_email = self.applicant_email_renderer.render_profile_completion_email(invitation_url=invitation_url)
        await commit_request_session()
        await self.email_sender.send_email(
            recipient_email=email,
            subject=rendered_email.subject,
            html_body=rendered_email.html_body,
        )


def _split_full_name(full_name: str) -> tuple[str | None, str]:
    parts = [part for part in full_name.strip().split() if part]
    if not parts:
        raise VolunteerApplicationValidationError("Navn er påkrevd.")
    if len(parts) == 1:
        return None, parts[0]
    return " ".join(parts[:-1]), parts[-1]


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _sanitize_filename(filename: str) -> str:
    stripped = filename.strip()
    if not stripped:
        return "photo"
    return stripped.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]


def _normalize_extension(filename: str) -> str:
    if "." not in filename:
        raise VolunteerApplicationConflictError("Photos must include a file extension.")
    return filename.rsplit(".", 1)[-1].lower()


def _resolve_content_type(filename: str, content_type: str | None) -> str:
    if content_type:
        return content_type
    extension = _normalize_extension(filename)
    if extension in {"jpg", "jpeg"}:
        return "image/jpeg"
    if extension == "png":
        return "image/png"
    if extension == "webp":
        return "image/webp"
    return "application/octet-stream"


def _build_photo_storage_path(filename_hash: str | None, extension: str | None) -> str | None:
    if not filename_hash or not extension:
        return None
    return f"{filename_hash}.{extension}"
