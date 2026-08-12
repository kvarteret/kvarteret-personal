from __future__ import annotations

import logging
from asyncio import to_thread
from typing import Any, Callable

from app.infrastructure.storage.protocols import StorageProtocol

logger = logging.getLogger(__name__)


class VolunteerApplicationSideEffects:
    def __init__(
        self,
        *,
        invalidate_pending_count_cache: Callable[[], None],
        storage_service: StorageProtocol | None = None,
    ) -> None:
        self.invalidate_pending_count_cache = invalidate_pending_count_cache
        self.storage_service = storage_service

    async def after_public_prospect_registered(
        self, result: Any, *, base_url: str | None
    ) -> None:
        self.invalidate_pending_count_cache()

    async def after_invited(self, invite: Any, *, base_url: str | None) -> None:
        return None

    async def after_submitted(self, detail: Any) -> None:
        self.invalidate_pending_count_cache()

    async def after_trial_started(
        self, detail: Any, *, base_url: str | None
    ) -> None:
        self.invalidate_pending_count_cache()

    async def after_approved(
        self, detail: Any, *, volunteer_id: int, base_url: str | None
    ) -> None:
        self.invalidate_pending_count_cache()
        return None

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
        return None


def _build_photo_storage_path(
    filename_hash: str | None, extension: str | None
) -> str | None:
    if not filename_hash or not extension:
        return None
    return f"{filename_hash}.{extension}"
