from __future__ import annotations

import json
import logging
import re
from asyncio import to_thread
from dataclasses import dataclass
from datetime import datetime
from urllib import error as urllib_error
from urllib import request as urllib_request

from app.config import Settings
from app.db.rate_limit import RateLimitExceeded, RateLimiter

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


class FeedbackDeliveryError(FeedbackError):
    pass


class FeedbackRateLimitedError(FeedbackError):
    pass


@dataclass(slots=True)
class FeedbackSubmission:
    category: str | None
    feedback_type: (
        str | None
    )  # "bug" | "feature" | "improvement", overrides category mapping
    name: str | None
    email: str | None
    message: str
    page: str
    platform: str | None
    user_id: int | None
    submitted_at: str
    source: str  # key into _SOURCE_PROJECT


class FeedbackService:
    def __init__(self, settings: Settings, rate_limiter: RateLimiter) -> None:
        self.settings = settings
        self.rate_limiter = rate_limiter

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
        source_key: str | None = None,
    ) -> None:
        # Counts before validation so a validation failure can't be used to
        # probe the limit for free (same TOCTOU-safety rationale as
        # mobile_card's rate limiting).
        rate_limit_key = source_key.strip() if source_key else "unknown"
        try:
            await self.rate_limiter.hit(
                f"feedback:submit:{rate_limit_key}",
                limit=self.settings.feedback_submission_limit,
                window_seconds=self.settings.feedback_submission_window_seconds,
            )
        except RateLimitExceeded:
            raise FeedbackRateLimitedError(
                "Too many feedback submissions. Try again later."
            ) from None

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
        await to_thread(_create_linear_issue, submission, self.settings)


def _validate_category(category: str | None) -> str | None:
    normalized = (category or "").strip().lower() or None
    if normalized and normalized not in {"ris", "ros", "forslag"}:
        raise FeedbackValidationError("Velg ris, ros eller forslag.")
    return normalized


def _validate_feedback_message(message: str) -> str:
    normalized = (message or "").strip()
    if not normalized:
        raise FeedbackValidationError("Du må skrive noe først. Ugetit?.")
    if len(normalized) > MAX_MESSAGE_LENGTH:
        raise FeedbackValidationError(
            f"Meldingen må være {MAX_MESSAGE_LENGTH} tegn eller kortere."
        )
    return normalized


def _validate_feedback_page(page: str) -> str:
    normalized = (page or "").strip() or "unknown"
    if len(normalized) > MAX_PAGE_LENGTH:
        raise FeedbackValidationError("Ugyldig side.")
    return normalized


def _validate_feedback_email(email: str | None) -> str | None:
    normalized = (email or "").strip() or None
    if normalized and len(normalized) > MAX_EMAIL_LENGTH:
        raise FeedbackValidationError(
            f"E-post må være {MAX_EMAIL_LENGTH} tegn eller kortere."
        )
    if normalized and not re.match(EMAIL_PATTERN, normalized):
        raise FeedbackValidationError("Skriv inn en gyldig e-postadresse.")
    return normalized


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
    normalized_category = _validate_category(category)
    normalized_message = _validate_feedback_message(message)
    normalized_page = _validate_feedback_page(page)
    normalized_email = _validate_feedback_email(email)

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


def _linear_graphql(
    api_key: str, query: str, variables: dict[str, object]
) -> dict[str, object]:
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib_request.Request(
        _GRAPHQL_ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": api_key,
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read())
    except urllib_error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        logger.exception("[linear] HTTP error %s: %s", exc.code, response_body[:1000])
        raise FeedbackDeliveryError("Linear request failed.") from exc
    except Exception as exc:
        logger.exception("[linear] Failed to call Linear")
        raise FeedbackDeliveryError("Linear request failed.") from exc

    errors = result.get("errors")
    if errors:
        logger.error("[linear] GraphQL errors: %s", errors)
        raise FeedbackDeliveryError("Linear returned GraphQL errors.")
    return result


def _create_linear_issue(submission: FeedbackSubmission, settings: Settings) -> None:
    api_key = settings.linear_api_key
    if not api_key:
        raise FeedbackDeliveryError("LINEAR_API_KEY is not configured.")

    project_attr, _ = _SOURCE_PROJECT.get(
        submission.source, ("linear_project_id_personal", "")
    )
    team_id = settings.linear_team_id
    project_id = getattr(settings, project_attr, None)

    missing_settings = [
        name
        for name, value in (
            ("LINEAR_TEAM_ID", team_id),
            (project_attr.upper(), project_id),
        )
        if not value
    ]
    if missing_settings:
        raise FeedbackDeliveryError(
            f"Incomplete Linear config: {', '.join(missing_settings)}."
        )

    variables = {
        "input": {
            "teamId": team_id,
            "projectId": project_id,
            "title": _derive_title(submission.message),
            "description": _build_description(submission),
        }
    }

    result = _linear_graphql(api_key, _CREATE_ISSUE_MUTATION, variables)

    issue_create = result.get("data", {}).get("issueCreate", {})
    if not issue_create.get("success"):
        logger.error("[linear] issueCreate returned success=false")
        raise FeedbackDeliveryError("Linear issueCreate returned success=false.")

    issue = issue_create.get("issue") or {}
    logger.info(
        "[linear] Created feedback issue",
        extra={
            "linear_issue_identifier": issue.get("identifier"),
            "linear_issue_url": issue.get("url"),
            "feedback_source": submission.source,
        },
    )
