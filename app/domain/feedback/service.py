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

_CUSTOMER_UPSERT_MUTATION = """
mutation CustomerUpsert($input: CustomerUpsertInput!) {
  customerUpsert(input: $input) {
    success
    customer { id }
  }
}
"""

_CUSTOMER_NEED_CREATE_MUTATION = """
mutation CustomerNeedCreate($input: CustomerNeedCreateInput!) {
  customerNeedCreate(input: $input) {
    success
    need { id }
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
        await to_thread(_create_linear_issue, submission, self.settings)


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


def _build_customer_request_body(submission: FeedbackSubmission) -> str:
    _, source_label = _SOURCE_PROJECT.get(submission.source, ("", "ukjent"))
    lines = [
        submission.message,
        "",
        "---",
        "",
        f"Source: {source_label}",
        f"Page: {submission.page}",
        f"Platform: {submission.platform or 'web'}",
        f"Submitted: {submission.submitted_at}",
    ]
    if submission.email:
        lines.append(f"Email: {submission.email}")
    if submission.name:
        lines.append(f"Name: {submission.name}")
    if submission.user_id:
        lines.append(f"User ID: {submission.user_id}")
    return "\n".join(lines)


def _customer_external_id(email: str) -> str:
    return f"kvarteret-feedback-email:{email.lower()}"


def _customer_name(submission: FeedbackSubmission) -> str:
    if submission.name and submission.email:
        return f"{submission.name} <{submission.email}>"
    return submission.name or submission.email or "Unknown feedback sender"


def _linear_graphql(api_key: str, query: str, variables: dict[str, object]) -> dict[str, object]:
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
        logger.error("[linear] HTTP error %s: %s", exc.code, response_body[:1000])
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

    project_attr, _ = _SOURCE_PROJECT.get(submission.source, ("linear_project_id_personal", ""))
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
        raise FeedbackDeliveryError(f"Incomplete Linear config: {', '.join(missing_settings)}.")

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
    _create_customer_request(api_key, submission, issue)


def _create_customer_request(
    api_key: str,
    submission: FeedbackSubmission,
    issue: dict[str, object],
) -> None:
    if not submission.email:
        return

    issue_id = issue.get("id")
    if not isinstance(issue_id, str) or not issue_id:
        logger.warning("[linear] Skipping customer request because issue id is missing")
        return

    external_id = _customer_external_id(submission.email)
    try:
        customer_result = _linear_graphql(
            api_key,
            _CUSTOMER_UPSERT_MUTATION,
            {
                "input": {
                    "name": _customer_name(submission),
                    "externalId": external_id,
                }
            },
        )
        customer_upsert = customer_result.get("data", {}).get("customerUpsert", {})
        if not customer_upsert.get("success"):
            logger.error("[linear] customerUpsert returned success=false")
            return

        customer = customer_upsert.get("customer") or {}
        customer_id = customer.get("id")
        if not isinstance(customer_id, str) or not customer_id:
            logger.warning("[linear] Skipping customer request because customer id is missing")
            return

        need_result = _linear_graphql(
            api_key,
            _CUSTOMER_NEED_CREATE_MUTATION,
            {
                "input": {
                    "issueId": issue_id,
                    "body": _build_customer_request_body(submission),
                    "customerId": customer_id,
                }
            },
        )
        customer_need_create = need_result.get("data", {}).get("customerNeedCreate", {})
        if not customer_need_create.get("success"):
            logger.error("[linear] customerNeedCreate returned success=false")
            return

        need = customer_need_create.get("need") or {}
        logger.info(
            "[linear] Created customer request",
            extra={
                "linear_customer_need_id": need.get("id"),
                "linear_issue_identifier": issue.get("identifier"),
                "feedback_source": submission.source,
            },
        )
    except FeedbackDeliveryError:
        logger.exception("[linear] Failed to create customer request")
