from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from app.config import Settings
from app.db.session import current_session
from app.domain.volunteer_applications.tables import (
    volunteer_application_group_members,
    volunteer_application_invites,
    volunteer_application_submissions,
)
from app.email_delivery import (
    APPLICANT_APPLICATION_RECEIVED,
    APPLICANT_INVITATION,
    APPLICANT_PROFILE_COMPLETION,
    VOLUNTEER_TEMPLATE_KEYS,
)
from app.infrastructure.email.applicant_templates import (
    ApplicantEmailTemplateRendererProtocol,
)


class EmailPreparationFailure(RuntimeError):
    def __init__(
        self, category: str, *, expired: bool = False, retryable: bool = False
    ) -> None:
        super().__init__(category)
        self.category = category
        self.expired = expired
        self.retryable = retryable


class PreparedEmail:
    def __init__(self, recipient_email: str, subject: str, html_body: str) -> None:
        self.recipient_email = recipient_email
        self.subject = subject
        self.html_body = html_body


class EmailMessagePreparer:
    """Resolve one queued email into the existing transport's message shape.

    This component owns template-specific reads and temporary secret handling.
    It does not enqueue, lease, retry, or send messages.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        applicant_renderer: ApplicantEmailTemplateRendererProtocol,
    ) -> None:
        self.settings = settings
        self.applicant_renderer = applicant_renderer

    async def prepare(self, delivery: Mapping[str, Any]) -> PreparedEmail:
        if delivery["template_version"] != 1:
            raise EmailPreparationFailure("unsupported_template_version")
        template_key = delivery["template_key"]
        if template_key in VOLUNTEER_TEMPLATE_KEYS:
            return await self._prepare_volunteer_email(delivery)
        raise EmailPreparationFailure("unknown_template")

    async def _prepare_volunteer_email(
        self, delivery: Mapping[str, Any]
    ) -> PreparedEmail:
        registration_id = delivery["registration_id"]
        if registration_id is None:
            raise EmailPreparationFailure("business_record_missing")
        invite = (
            (
                await _session().execute(
                    select(
                        volunteer_application_invites.c.token,
                        volunteer_application_invites.c.email,
                        volunteer_application_invites.c.first_choice_label,
                        volunteer_application_group_members.c.group_id,
                    )
                    .select_from(
                        volunteer_application_invites.outerjoin(
                            volunteer_application_group_members,
                            volunteer_application_group_members.c.invite_id
                            == volunteer_application_invites.c.id,
                        )
                    )
                    .where(volunteer_application_invites.c.id == registration_id)
                    .limit(1)
                )
            )
            .mappings()
            .first()
        )
        if invite is None:
            raise EmailPreparationFailure("business_record_missing")
        if delivery["template_key"] == APPLICANT_APPLICATION_RECEIVED:
            rendered = self.applicant_renderer.render_application_received_email()
            return PreparedEmail(
                invite["email"], rendered.subject, rendered.html_body
            )
        base_url = (self.settings.app_public_base_url or "").rstrip("/")
        if not base_url:
            raise EmailPreparationFailure("public_base_url_missing")
        invitation_url = f"{base_url}/apply/{invite['token']}"
        if delivery["template_key"] == APPLICANT_INVITATION:
            rendered = self.applicant_renderer.render_invitation_email(
                invitation_url=invitation_url
            )
        elif delivery["template_key"] == APPLICANT_PROFILE_COMPLETION:
            rendered = self.applicant_renderer.render_profile_completion_email(
                invitation_url=invitation_url
            )
        else:
            inviter = await self._load_friend_inviter(invite["group_id"])
            if inviter is None:
                raise EmailPreparationFailure("inviter_record_missing")
            rendered = self.applicant_renderer.render_friend_invitation_email(
                invitation_url=invitation_url,
                inviter_name=inviter["name"],
                first_choice_group_name=invite["first_choice_label"] or "Kvarteret",
            )
        return PreparedEmail(invite["email"], rendered.subject, rendered.html_body)

    async def _load_friend_inviter(self, group_id: int | None) -> dict[str, str] | None:
        if group_id is None:
            return None
        row = (
            (
                await _session().execute(
                    select(
                        volunteer_application_submissions.c.first_name,
                        volunteer_application_submissions.c.last_name,
                    )
                    .select_from(
                        volunteer_application_group_members.join(
                            volunteer_application_submissions,
                            volunteer_application_submissions.c.invite_id
                            == volunteer_application_group_members.c.invite_id,
                        )
                    )
                    .where(
                        volunteer_application_group_members.c.group_id == group_id,
                        volunteer_application_group_members.c.role == "inviter",
                    )
                    .limit(1)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return {"name": " ".join(filter(None, [row["first_name"], row["last_name"]]))}

def _session():
    session = current_session()
    if session is None:
        raise RuntimeError("Email preparation requires an active database session.")
    return session
