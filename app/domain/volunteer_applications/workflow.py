from __future__ import annotations

from typing import Any, Protocol


class VolunteerApplicationWorkflowOperations(Protocol):
    async def create_public_prospect_registration_record(
        self, registration: Any, *, base_url: str | None
    ) -> Any: ...
    async def create_invitation_record(
        self,
        email: str,
        *,
        initial_group_id: int | None,
        initial_role_id: int | None,
    ) -> Any: ...
    async def submit_application_record(
        self,
        token: str,
        submission: Any,
        *,
        base_url: str | None,
        photo_filename: str | None,
        photo_content: bytes | None,
        photo_content_type: str | None,
    ) -> Any: ...
    async def mark_trial_shift_attended_record(
        self, registration_id: int, *, attended: bool
    ) -> Any: ...
    async def approve_application_record(
        self, registration_id: int, *, accepted_group_id: int | None
    ) -> tuple[Any, int]: ...
    async def drop_group_invitee_record(
        self, registration_id: int, *, dropped_by_user_id: int | None
    ) -> Any: ...
    async def delete_application_record(self, registration_id: int) -> Any: ...
    async def resend_invitation_record(self, registration_id: int) -> Any: ...
    async def get_volunteer_application_detail(
        self, registration_id: int
    ) -> Any | None: ...


class VolunteerApplicationSideEffectsProtocol(Protocol):
    async def after_public_prospect_registered(
        self, result: Any, *, base_url: str | None
    ) -> None: ...
    async def after_invited(self, invite: Any, *, base_url: str | None) -> None: ...
    async def after_submitted(self, detail: Any) -> None: ...
    async def after_trial_shift_marked(self, detail: Any) -> None: ...
    async def after_approved(
        self, detail: Any, *, volunteer_id: int, base_url: str | None
    ) -> None: ...
    async def after_group_invitee_dropped(self, detail: Any) -> None: ...
    async def after_deleted(self, detail: Any) -> None: ...
    async def after_invitation_resent(
        self, detail: Any, *, base_url: str | None
    ) -> None: ...


class VolunteerApplicationWorkflow:
    def __init__(
        self,
        *,
        operations: VolunteerApplicationWorkflowOperations,
        side_effects: VolunteerApplicationSideEffectsProtocol,
    ) -> None:
        self.operations = operations
        self.side_effects = side_effects

    async def invite(
        self,
        email: str,
        *,
        base_url: str | None,
        initial_group_id: int | None,
        initial_role_id: int | None,
    ) -> Any:
        invite = await self.operations.create_invitation_record(
            email,
            initial_group_id=initial_group_id,
            initial_role_id=initial_role_id,
        )
        try:
            await self.side_effects.after_invited(invite, base_url=base_url)
        except Exception:
            await self.operations.delete_application_record(invite.registration_id)
            raise
        return invite

    async def register_public_prospect(
        self, registration: Any, *, base_url: str | None
    ) -> Any:
        result = await self.operations.create_public_prospect_registration_record(
            registration, base_url=base_url
        )
        await self.side_effects.after_public_prospect_registered(
            result, base_url=base_url
        )
        return result.detail

    async def submit(
        self,
        token: str,
        submission: Any,
        *,
        base_url: str | None,
        photo_filename: str | None,
        photo_content: bytes | None,
        photo_content_type: str | None,
    ) -> Any:
        detail = await self.operations.submit_application_record(
            token,
            submission,
            base_url=base_url,
            photo_filename=photo_filename,
            photo_content=photo_content,
            photo_content_type=photo_content_type,
        )
        await self.side_effects.after_submitted(detail)
        return detail

    async def mark_trial_shift_attended(
        self, registration_id: int, *, attended: bool
    ) -> Any:
        detail = await self.operations.mark_trial_shift_attended_record(
            registration_id, attended=attended
        )
        await self.side_effects.after_trial_shift_marked(detail)
        return detail

    async def approve(
        self,
        registration_id: int,
        *,
        accepted_group_id: int | None,
        base_url: str | None,
    ) -> int:
        detail, volunteer_id = await self.operations.approve_application_record(
            registration_id, accepted_group_id=accepted_group_id
        )
        await self.side_effects.after_approved(
            detail, volunteer_id=volunteer_id, base_url=base_url
        )
        return volunteer_id

    async def drop_group_invitee(
        self, registration_id: int, *, dropped_by_user_id: int | None
    ) -> None:
        detail = await self.operations.drop_group_invitee_record(
            registration_id, dropped_by_user_id=dropped_by_user_id
        )
        await self.side_effects.after_group_invitee_dropped(detail)

    async def delete(self, registration_id: int) -> None:
        detail = await self.operations.delete_application_record(registration_id)
        await self.side_effects.after_deleted(detail)

    async def resend_invitation(
        self, registration_id: int, *, base_url: str | None
    ) -> Any:
        detail = await self.operations.resend_invitation_record(registration_id)
        await self.side_effects.after_invitation_resent(detail, base_url=base_url)
        return detail
