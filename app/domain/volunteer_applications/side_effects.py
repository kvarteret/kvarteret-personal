from __future__ import annotations

import logging
from asyncio import to_thread
from typing import Any, Awaitable, Callable
from app.infrastructure.storage.protocols import StorageProtocol

logger = logging.getLogger(__name__)

SendInvitationEmail = Callable[..., Awaitable[None]]
SendFriendInvitationEmail = Callable[..., Awaitable[None]]
SendProfileCompletionEmail = Callable[..., Awaitable[None]]
SendApplicationReceivedEmail = Callable[..., Awaitable[None]]


class VolunteerApplicationSideEffects:
    def __init__(
        self,
        *,
        invalidate_pending_count_cache: Callable[[], None],
        send_invitation_email: SendInvitationEmail,
        send_friend_invitation_email: SendFriendInvitationEmail,
        send_profile_completion_email: SendProfileCompletionEmail,
        send_application_received_email: SendApplicationReceivedEmail,
        storage_service: StorageProtocol | None = None,
    ) -> None:
        self.invalidate_pending_count_cache = invalidate_pending_count_cache
        self.send_invitation_email = send_invitation_email
        self.send_friend_invitation_email = send_friend_invitation_email
        self.send_profile_completion_email = send_profile_completion_email
        self.send_application_received_email = send_application_received_email
        self.storage_service = storage_service

    async def after_public_prospect_registered(
        self, result: Any, *, base_url: str | None
    ) -> None:
        self.invalidate_pending_count_cache()
        try:
            await self.send_application_received_email(email=result.detail.email)
        except Exception:
            logger.exception(
                "Failed to send application receipt email for registration %s",
                result.detail.registration_id,
            )
        for invite in result.friend_invites:
            try:
                await self.send_friend_invitation_email(
                    email=invite.email,
                    token=invite.token,
                    inviter_name=invite.inviter_name,
                    first_choice_group_name=invite.first_choice_group_name,
                    base_url=base_url,
                )
            except Exception:
                logger.exception(
                    "Failed to send group volunteer invitation email for registration %s",
                    invite.registration_id,
                )

    async def after_invited(self, invite: Any, *, base_url: str | None) -> None:
        await self.send_invitation_email(
            email=invite.email,
            token=invite.token,
            base_url=base_url,
        )

    async def after_submitted(self, detail: Any) -> None:
        self.invalidate_pending_count_cache()

    async def after_trial_started(
        self, detail: Any, *, base_url: str | None
    ) -> None:
        self.invalidate_pending_count_cache()
        await self.send_profile_completion_email(
            email=detail.email,
            token=detail.token,
            base_url=base_url,
        )

    async def after_approved(
        self, detail: Any, *, volunteer_id: int, base_url: str | None
    ) -> None:
        self.invalidate_pending_count_cache()
        return None

    async def after_group_invitee_dropped(self, detail: Any) -> None:
        self.invalidate_pending_count_cache()

    async def after_deleted(self, detail: Any) -> None:
        self.invalidate_pending_count_cache()
        storage_path = _build_photo_storage_path(detail.photo_sha1, detail.photo_filetype)
        if storage_path is None or self.storage_service is None:
            return
        try:
            await to_thread(self.storage_service.remove_photo, storage_path)
        except Exception:
            logger.exception(
                "Failed to remove photo for deleted volunteer application %s",
                detail.registration_id,
            )

    async def after_invitation_resent(
        self, detail: Any, *, base_url: str | None
    ) -> None:
        await self.send_invitation_email(
            email=detail.email,
            token=detail.token,
            base_url=base_url,
        )


def _build_photo_storage_path(
    filename_hash: str | None, extension: str | None
) -> str | None:
    if not filename_hash or not extension:
        return None
    return f"{filename_hash}.{extension}"
