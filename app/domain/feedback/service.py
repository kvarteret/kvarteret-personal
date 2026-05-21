from __future__ import annotations

import json
import logging
import re
from asyncio import to_thread
from dataclasses import dataclass
from datetime import datetime
from urllib import request as urllib_request

from app.config import Settings

logger = logging.getLogger(__name__)

EMAIL_PATTERN = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
MAX_EMAIL_LENGTH = 254
MAX_MESSAGE_LENGTH = 2000
MAX_PAGE_LENGTH = 200

_GRAPHQL_ENDPOINT = "https://api.linear.app/graphql"

_CREATE_ISSUE_MUTATION = """
mutation CreateIssue($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier url }
  }
}
"""

_CATEGORY_TO_TYPE = {
    "ris": "bug",
    "forslag": "feature",
    "ros": "improvement",
}

# Maps the `source` field to (settings attribute name, human-readable label)
_SOURCE_PROJECT = {
    "personalplattformen": ("linear_project_id_personal", "Personalplattformen"),
    "internbevis-rn": ("linear_project_id_internbevis", "internbevis-appen"),
    "nettside": ("linear_project_id_nettside", "kvarteret.no"),
}


class FeedbackError(RuntimeError):
    pass


class FeedbackValidationError(FeedbackError):
    pass


@dataclass(slots=True)
class FeedbackSubmission:
    category: str | None
    feedback_type: str | None  # "bug" | "feature" | "improvement", overrides category mapping
    name: str | None
    email: str | None
    message: str
    page: str
    platform: str | None
    user_id: int | None
    submitted_at: str
    source: str  # key into _SOURCE_PROJECT


class FeedbackService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def submit_feedback(
        self,
        *,
        category: str | None = None,
        feedback_type: str | None = None,
        name: str | None,
        email: str | None,
        message: str,
        page: str,
        platform: str | None = None,
        user_id: int | None = None,
        source: str = "personalplattformen",
    ) -> None:
        submission = _normalize_submission(
            category=category,
            feedback_type=feedback_type,
            name=name,
            email=email,
            message=message,
            page=page,
            platform=platform,
            user_id=user_id,
            source=source,
        )
        try:
            await to_thread(_create_linear_issue, submission, self.settings)
        except Exception:
            logger.exception("[linear] Failed to create feedback issue")


def _normalize_submission(
    *,
    category: str | None,
    feedback_type: str | None,
    name: str | None,
    email: str | None,
    message: str,
    page: str,
    platform: str | None,
    user_id: int | None,
    source: str,
) -> FeedbackSubmission:
    normalized_category = (category or "").strip().lower() or None
    if normalized_category and normalized_category not in {"ris", "ros", "forslag"}:
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
    if normalized_email and not re.match(EMAIL_PATTERN, normalized_email):
        raise FeedbackValidationError("Skriv inn en gyldig e-postadresse.")

    submitted_at = datetime.now().astimezone().strftime("%d.%m.%Y %H:%M")
    normalized_source = source if source in _SOURCE_PROJECT else "personalplattformen"
    _valid_types = {"bug", "feature", "improvement"}
    normalized_type = feedback_type if feedback_type in _valid_types else None
    return FeedbackSubmission(
        category=normalized_category,
        feedback_type=normalized_type,
        name=(name or "").strip() or None,
        email=normalized_email,
        message=normalized_message,
        page=normalized_page,
        platform=(platform or "").strip() or None,
        user_id=user_id,
        submitted_at=submitted_at,
        source=normalized_source,
    )


def _derive_title(message: str) -> str:
    first_sentence = re.split(r"[.!?]\s", message)[0].strip()
    if len(first_sentence) <= 80:
        return first_sentence
    return first_sentence[:77] + "..."


def _build_description(submission: FeedbackSubmission) -> str:
    _, source_label = _SOURCE_PROJECT.get(submission.source, ("", "ukjent"))
    lines = [
        submission.message,
        "",
        "---",
        "",
        f"**Kilde:** {source_label}",
        f"**Side:** {submission.page}",
        f"**Plattform:** {submission.platform or 'web'}",
        f"**Sendt:** {submission.submitted_at}",
    ]
    if submission.name:
        lines.append(f"**Navn:** {submission.name}")
    if submission.user_id:
        lines.append(f"**Bruker-ID:** {submission.user_id}")
    if submission.email:
        lines.append(f"**E-post:** {submission.email}")
    return "\n".join(lines)


def _create_linear_issue(submission: FeedbackSubmission, settings: Settings) -> None:
    api_key = settings.linear_api_key
    if not api_key:
        logger.error("[linear] LINEAR_API_KEY is not configured — skipping issue creation")
        return

    project_attr, _ = _SOURCE_PROJECT.get(submission.source, ("linear_project_id_personal", ""))
    team_id = settings.linear_team_id
    project_id = getattr(settings, project_attr, None)
    state_id = settings.linear_state_id_triage

    if not team_id or not project_id or not state_id:
        logger.error("[linear] Incomplete config — run scripts/bootstrap-linear.ts to populate IDs")
        return

    variables = {
        "input": {
            "teamId": team_id,
            "projectId": project_id,
            "stateId": state_id,
            "title": _derive_title(submission.message),
            "description": _build_description(submission),
        }
    }

    body = json.dumps({"query": _CREATE_ISSUE_MUTATION, "variables": variables}).encode("utf-8")
    req = urllib_request.Request(
        _GRAPHQL_ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=10) as response:
        result = json.loads(response.read())

    errors = result.get("errors")
    if errors:
        logger.error("[linear] GraphQL errors: %s", errors)
        return

    if not result.get("data", {}).get("issueCreate", {}).get("success"):
        logger.error("[linear] issueCreate returned success=false")
