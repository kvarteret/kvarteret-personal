from __future__ import annotations

import json
from asyncio import to_thread
from dataclasses import dataclass
from datetime import datetime
from urllib import request as urllib_request

from app.config import Settings
from app.errors import NotConfiguredError

EMAIL_PATTERN = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
MAX_EMAIL_LENGTH = 254
MAX_MESSAGE_LENGTH = 2000
MAX_PAGE_LENGTH = 200


class FeedbackError(RuntimeError):
    pass


class FeedbackValidationError(FeedbackError):
    pass


@dataclass(slots=True)
class FeedbackSubmission:
    category: str
    name: str | None
    email: str | None
    message: str
    page: str
    submitted_at: str


class FeedbackService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def submit_feedback(
        self,
        *,
        category: str,
        name: str | None,
        email: str | None,
        message: str,
        page: str,
    ) -> None:
        webhook_url = self.settings.slack_feedback_webhook_url
        if not webhook_url:
            raise NotConfiguredError("Feedback webhook is not configured.")

        submission = _normalize_submission(
            category=category,
            name=name,
            email=email,
            message=message,
            page=page,
        )
        payload = _build_slack_payload(submission)
        await to_thread(_post_to_slack, webhook_url, payload)


def _normalize_submission(*, category: str, name: str | None, email: str | None, message: str, page: str) -> FeedbackSubmission:
    normalized_category = (category or "").strip().lower()
    if normalized_category not in {"ris", "ros", "forslag"}:
        raise FeedbackValidationError("Velg ris, ros eller forslag.")

    normalized_message = (message or "").strip()
    if not normalized_message:
        raise FeedbackValidationError("Du må skrive noe først. Ugetit?.")
    if len(normalized_message) > MAX_MESSAGE_LENGTH:
        raise FeedbackValidationError(f"Meldingen må være {MAX_MESSAGE_LENGTH} tegn eller kortere.")

    normalized_page = (page or "").strip() or "unknown"
    if len(normalized_page) > MAX_PAGE_LENGTH:
        raise FeedbackValidationError("Ugyldig side.")

    normalized_email = (email or "").strip() or None
    if normalized_email and len(normalized_email) > MAX_EMAIL_LENGTH:
        raise FeedbackValidationError(f"E-post må være {MAX_EMAIL_LENGTH} tegn eller kortere.")
    if normalized_email and not _is_valid_email(normalized_email):
        raise FeedbackValidationError("Skriv inn en gyldig e-postadresse.")

    normalized_name = (name or "").strip() or None

    submitted_at = datetime.now().astimezone().strftime("%d.%m.%Y %H:%M")
    return FeedbackSubmission(
        category=normalized_category,
        name=normalized_name,
        email=normalized_email,
        message=normalized_message,
        page=normalized_page,
        submitted_at=submitted_at,
    )


def _is_valid_email(value: str) -> bool:
    import re

    return bool(re.match(EMAIL_PATTERN, value))


def _build_slack_payload(submission: FeedbackSubmission) -> dict:
    name_value = _escape_slack(submission.name) if submission.name else "_Ikke oppgitt_"
    email_value = _escape_slack(submission.email) if submission.email else "_Ikke oppgitt_"
    category_label = submission.category.capitalize()
    return {
        "text": f"Ny {submission.category} fra {submission.page}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Ny tilbakemelding til Personalplattformen",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Type*\n{_escape_slack(category_label)}"},
                    {"type": "mrkdwn", "text": f"*Side*\n{_escape_slack(submission.page)}"},
                    {"type": "mrkdwn", "text": f"*Navn*\n{name_value}"},
                    {"type": "mrkdwn", "text": f"*E-post*\n{email_value}"},
                    {"type": "mrkdwn", "text": f"*Sendt*\n{_escape_slack(submission.submitted_at)}"},
                ],
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Melding*\n{_escape_slack(submission.message)}",
                },
            },
        ],
    }


def _escape_slack(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _post_to_slack(webhook_url: str, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(request) as response:
        if response.status < 200 or response.status >= 300:
            raise FeedbackError(f"Slack webhook failed with status {response.status}.")
