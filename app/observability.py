from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
from collections import Counter
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from opentelemetry import metrics, trace

from app.auth.models import AuthenticatedUser
from app.config import Settings

_request_context: ContextVar[dict[str, Any]] = ContextVar("request_context", default={})
_diagnostic_counters: Counter[str] = Counter()
_MAX_DIAGNOSTIC_COUNTER_KEYS = 32
_meter = metrics.get_meter("kvarteret-personal")
_diagnostic_metric = _meter.create_counter("telemetry.projection.failures")
_request_duration = _meter.create_histogram("app.http.request.duration", unit="ms")
_operation_duration = _meter.create_histogram("app.operation.duration", unit="ms")

# The root logger stays at settings.log_level, so application logs still emit at INFO by default.
# Only these specific third-party loggers are overridden to WARNING to reduce Vercel noise.
_NOISY_LOGGER_LEVELS: dict[str, int] = {
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "azure": logging.WARNING,
    "azure.core": logging.WARNING,
    "azure.storage": logging.WARNING,
    "azure.core.pipeline.policies.http_logging_policy": logging.WARNING,
    "opentelemetry": logging.WARNING,
}

_COMMON_FIELDS = frozenset(
    {
        "event_id",
        "schema_version",
        "occurred_at",
        "service",
        "environment",
        "request_id",
        "trace_id",
        "span_id",
        "registration_id",
        "origin_trace_id",
        "volunteer_id",
        "group_id",
        "course_id",
        "subject_type",
        "subject_id",
        "email_delivery_id",
        "template_key",
        "status",
        "status_code",
        "outcome",
        "reason_code",
        "operation_id",
        "attempt_id",
        "provider_http_status",
        "failure_stage",
        "error_category",
        "smtp_status_class",
        "attempt_no",
        "duration_ms",
        "http_method",
        "route_template",
        "platform",
        "source",
        "form_id",
        "attempt_count",
        "validation_fields",
        "validation_codes",
        "validation_issue_count",
        "user_account_id",
        "role",
        "count",
        "claimed_count",
        "sent_count",
        "failed_count",
        "retrying_count",
        "interrupted_count",
    }
)

# Every event-specific field is declared here. Callers cannot add arbitrary data.
_EVENT_FIELDS: dict[str, frozenset[str]] = {
    "admin.activity": frozenset(
        {
            "action",
            "subject_type",
            "subject_id",
            "admin_user_account_id",
            "admin_role",
            "role",
            "delivery",
            "setup_url_created",
            "enabled",
            "impersonated_user_account_id",
        }
    ),
    "app.operation.timing": frozenset(
        {"operation", "limit", "semester_code", "query_present"}
    ),
    "http.validation.failed": frozenset(
        {"validation_fields", "validation_codes", "validation_issue_count"}
    ),
    "form.submission.repeated_failure": frozenset(
        {
            "form_id",
            "attempt_count",
            "validation_fields",
            "validation_codes",
            "error_source",
        }
    ),
    "email.delivery.queued": frozenset(),
    "email.delivery.accepted": frozenset(),
    "email.delivery.retry_scheduled": frozenset(),
    "email.delivery.failed": frozenset(),
    "email.delivery.unexpected": frozenset(),
    "volunteer.prospect.conflict": frozenset({"conflict_type"}),
    "web.client_error": frozenset({"error_type", "error_source"}),
    "mobile_card.session.logout": frozenset(
        {
            "app_version",
            "auth_error_code",
            "auth_error_status",
            "event_name",
            "execution_environment",
            "had_cached_user",
            "had_login_marker",
            "had_stored_credentials",
            "platform",
            "runtime_version",
            "update_channel",
            "update_id",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class EventDefinition:
    message: str
    level: int = logging.INFO
    default_outcome: str = "success"


# The catalog is deliberately local to the service. It is the reviewable source
# for readable log bodies; callers may only provide the typed fields below.
_EVENT_CATALOG: dict[str, EventDefinition] = {
    "admin.activity": EventDefinition("Administrative action completed"),
    "app.operation.timing": EventDefinition(
        "Application operation completed", logging.DEBUG
    ),
    "email.dispatch.deferred": EventDefinition(
        "Email dispatch deferred", logging.WARNING, "failure"
    ),
    "email.delivery.queued": EventDefinition("Email delivery queued"),
    "email.delivery.accepted": EventDefinition("Email accepted by mail server"),
    "email.delivery.retry_scheduled": EventDefinition(
        "Email delivery retry scheduled", logging.WARNING, "retry_scheduled"
    ),
    "email.delivery.failed": EventDefinition(
        "Email delivery failed", logging.ERROR, "failure"
    ),
    "email.delivery.unexpected": EventDefinition(
        "Unexpected email delivery failure", logging.ERROR, "failure"
    ),
    "volunteer.prospect.conflict": EventDefinition(
        "Volunteer prospect registration conflicted", logging.WARNING, "failure"
    ),
    "volunteer.prospect.registered": EventDefinition("Volunteer prospect registered"),
    "volunteer.application.invited": EventDefinition(
        "Volunteer application invitation created"
    ),
    "volunteer.application.submitted": EventDefinition(
        "Volunteer application submitted"
    ),
    "volunteer.application.profile_completed": EventDefinition(
        "Volunteer application profile completed"
    ),
    "volunteer.application.contacted": EventDefinition("Volunteer applicant contacted"),
    "volunteer.application.trial_started": EventDefinition(
        "Volunteer trial shift started"
    ),
    "volunteer.application.approved": EventDefinition("Volunteer application approved"),
    "volunteer.application.rejected": EventDefinition("Volunteer application rejected"),
    "volunteer.application.reopened": EventDefinition("Volunteer application reopened"),
    "volunteer.application.volunteer_restored": EventDefinition(
        "Volunteer status restored"
    ),
    "volunteer.application.deleted": EventDefinition("Volunteer application deleted"),
    "volunteer.application.invitation_resent": EventDefinition(
        "Volunteer invitation resent"
    ),
    "volunteer.application.transitioned": EventDefinition(
        "Volunteer application transition completed"
    ),
    "mobile_card.access_code.requested": EventDefinition(
        "Mobile-card access code requested"
    ),
    "mobile_card.session.created": EventDefinition("Mobile-card session created"),
    "mobile_card.session.rejected": EventDefinition(
        "Mobile-card session rejected", logging.WARNING, "failure"
    ),
    "mobile_card.session.renewed": EventDefinition(
        "Mobile-card session renewed", logging.DEBUG
    ),
    "mobile_card.session.read": EventDefinition(
        "Mobile-card session read", logging.DEBUG
    ),
    "mobile_card.session.expired": EventDefinition(
        "Mobile-card session expired", default_outcome="failure"
    ),
    "mobile_card.session.invalid": EventDefinition(
        "Mobile-card session rejected", logging.WARNING, "failure"
    ),
    "mobile_card.identity.resolved": EventDefinition(
        "Authenticated mobile-card session matched to subject"
    ),
    "mobile_card.client_session_invalidated": EventDefinition(
        "Mobile app reported an invalid session", logging.WARNING, "failure"
    ),
    "mobile_card.client_credentials_missing": EventDefinition(
        "Mobile app reported missing stored credentials", logging.WARNING, "failure"
    ),
    "web.client_error": EventDefinition(
        "Web client error reported", logging.WARNING, "failure"
    ),
    "http.validation.failed": EventDefinition(
        "HTTP validation failed", logging.WARNING, "failure"
    ),
    "form.submission.repeated_failure": EventDefinition(
        "Repeated form submission failure", logging.ERROR, "failure"
    ),
    "auth.login.failed": EventDefinition("Login failed", logging.WARNING, "failure"),
    "auth.login.succeeded": EventDefinition("Login succeeded"),
    "auth.login.throttled": EventDefinition(
        "Login throttled", logging.WARNING, "failure"
    ),
    "http.request.failed": EventDefinition(
        "HTTP request failed", logging.ERROR, "failure"
    ),
    "http.request.slow": EventDefinition(
        "Slow HTTP request", logging.WARNING, "unknown"
    ),
    "telemetry.configuration.failed": EventDefinition(
        "Telemetry configuration failed", logging.WARNING, "failure"
    ),
}

_ALLOWED_OUTCOMES = frozenset({"success", "failure", "retry_scheduled", "unknown"})
_ALLOWED_REASON_CODES: dict[str, frozenset[str]] = {
    "auth.login.failed": frozenset({"account_not_found", "invalid_credentials"}),
    "auth.login.throttled": frozenset({"rate_limited"}),
    "mobile_card.session.rejected": frozenset({"invalid_access_code"}),
    "mobile_card.session.expired": frozenset({"expired"}),
    "mobile_card.session.invalid": frozenset({"bad_signature", "malformed"}),
}
_ALLOWED_FIELD_VALUES: dict[str, dict[str, frozenset[str]]] = {
    "volunteer.prospect.conflict": {
        "conflict_type": frozenset(
            {
                "application_conflict",
                "existing_volunteer",
                "active_application",
                "field_conflict",
                "idempotency_key_content_mismatch",
                "friend_email_existing_volunteer",
                "friend_email_active_application",
            }
        )
    },
    "mobile_card.session.renewed": {
        "subject_type": frozenset({"review", "trial_application", "volunteer"})
    },
    "mobile_card.session.created": {
        "subject_type": frozenset({"review", "trial_application", "volunteer"})
    },
    "mobile_card.session.read": {
        "subject_type": frozenset({"review", "trial_application", "volunteer"})
    },
    "mobile_card.identity.resolved": {
        "subject_type": frozenset({"review", "trial_application", "volunteer"})
    },
}
_MAX_STRING_FIELD_LENGTH = 512


class DomainLogger:
    """Small adapter that keeps domain-event policy out of call sites."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def event(
        self,
        event: str,
        *,
        fields: Mapping[str, object] | None = None,
        event_id: str | UUID | None = None,
        occurred_at: datetime | None = None,
        **typed_fields: object,
    ) -> None:
        event_fields = dict(fields or {})
        event_fields.update(typed_fields)
        emit_event(self._logger, event, fields=event_fields, event_id=event_id, occurred_at=occurred_at)

    def __getattr__(self, name: str):
        return getattr(self._logger, name)


def get_domain_logger(name: str) -> DomainLogger:
    return DomainLogger(logging.getLogger(name))


_FORBIDDEN_KEY_PARTS = (
    "authorization",
    "cookie",
    "email",
    "password",
    "phone",
    "secret",
    "token",
    "username",
    "body",
    "message",
    "url",
    "client_ip",
    "user_agent",
)
_EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_QUERY_PATTERN = re.compile(r"\?[^\s\"']+")
_TOKEN_PATH_PATTERN = re.compile(r"(/(?:apply|set-password)/)[^/?#\s]+", re.I)


def current_trace_fields() -> dict[str, str]:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return {}
    return {
        "trace_id": format(context.trace_id, "032x"),
        "span_id": format(context.span_id, "016x"),
    }


def current_trace_id() -> str | None:
    return current_trace_fields().get("trace_id")


def _is_safe_scalar(value: object) -> bool:
    return value is None or isinstance(value, (bool, int, float, str, UUID))


_ENVELOPE_FIELDS = frozenset({
    "event_id", "schema_version", "occurred_at", "service", "environment",
    "request_id", "trace_id", "span_id", "outcome",
})
_DOMAIN_FIELDS = {
    "email": frozenset({"email_delivery_id", "registration_id", "template_key",
        "attempt_no", "attempt_id", "operation_id", "duration_ms", "failure_stage",
        "error_category", "smtp_status_class", "provider_http_status"}),
    "volunteer": frozenset({"registration_id", "volunteer_id", "origin_trace_id"}),
    "mobile": frozenset({"subject_type", "subject_id", "reason_code", "duration_ms"}),
}


def _allowed_fields(event: str) -> frozenset[str]:
    if event.startswith("email.delivery."):
        return _ENVELOPE_FIELDS | _DOMAIN_FIELDS["email"]
    if event.startswith("volunteer.application.") or event == "volunteer.prospect.registered":
        return _ENVELOPE_FIELDS | _DOMAIN_FIELDS["volunteer"]
    if event.startswith("mobile_card.client_"):
        return _ENVELOPE_FIELDS | {"platform", "source"}
    if event.startswith("mobile_card.") and event != "mobile_card.session.logout":
        return _ENVELOPE_FIELDS | _DOMAIN_FIELDS["mobile"]
    if event.startswith("auth.login."):
        return _ENVELOPE_FIELDS | {"reason_code", "user_account_id", "role"}
    return _COMMON_FIELDS | _EVENT_FIELDS.get(event, frozenset())


def _required_fields(event: str) -> frozenset[str]:
    if event.startswith("email.delivery."):
        return frozenset({"email_delivery_id"})
    if event.startswith("volunteer.application.") or event == "volunteer.prospect.registered":
        return frozenset({"registration_id"})
    if event in _ALLOWED_REASON_CODES:
        return frozenset({"reason_code"})
    if event in {"mobile_card.session.created", "mobile_card.identity.resolved"}:
        return frozenset({"subject_type", "subject_id"})
    if event.startswith("mobile_card.client_"):
        return frozenset({"source", "platform"})
    return frozenset()


def sanitize_fields(event: str, values: Mapping[str, object]) -> dict[str, object]:
    return _sanitize_fields(event, values, reject_invalid=False)[0]


def _sanitize_fields(
    event: str,
    values: Mapping[str, object],
    *,
    reject_invalid: bool,
) -> tuple[dict[str, object], bool]:
    allowed = _allowed_fields(event)
    sanitized: dict[str, object] = {}
    valid = True
    if reject_invalid and any(values.get(key) is None for key in _required_fields(event)):
        _record_diagnostic("missing_field")
        valid = False
    numeric_fields = {"registration_id", "volunteer_id", "user_account_id", "attempt_no",
        "duration_ms", "status_code", "provider_http_status", "schema_version", "smtp_status_class"}
    for key, value in values.items():
        if not isinstance(key, str):
            _record_diagnostic("invalid_field")
            valid = False
            continue
        normalized_key = key.strip()
        if normalized_key not in allowed:
            _record_diagnostic("invalid_field")
            valid = False
            continue
        if value is not None and normalized_key in numeric_fields and (
            not isinstance(value, (int, float)) or isinstance(value, bool)
            or value < 0 or (normalized_key != "duration_ms" and not isinstance(value, int))
        ):
            _record_diagnostic("invalid_field")
            valid = False
            continue
        if normalized_key in {"source", "platform"} and event.startswith("mobile_card.client_") and value not in (
            {"client"} if normalized_key == "source" else {"ios", "android", "web", "other"}
        ):
            _record_diagnostic("invalid_enum")
            valid = False
            continue
        if not _is_safe_scalar(value):
            _record_diagnostic("invalid_field")
            valid = False
            continue
        if isinstance(value, float) and not math.isfinite(value):
            _record_diagnostic("invalid_field")
            valid = False
            continue
        if isinstance(value, str) and len(value) > _MAX_STRING_FIELD_LENGTH:
            _record_diagnostic("invalid_field")
            valid = False
            continue
        if normalized_key != "email_delivery_id" and any(
            part in normalized_key.lower() for part in _FORBIDDEN_KEY_PARTS
        ):
            _record_diagnostic("invalid_field")
            valid = False
            continue
        if normalized_key == "outcome" and value not in _ALLOWED_OUTCOMES:
            _record_diagnostic("invalid_outcome")
            valid = False
            continue
        allowed_reason_codes = _ALLOWED_REASON_CODES.get(event)
        if (
            normalized_key == "reason_code"
            and allowed_reason_codes is not None
            and value not in allowed_reason_codes
        ):
            _record_diagnostic("invalid_reason_code")
            valid = False
            continue
        allowed_values = _ALLOWED_FIELD_VALUES.get(event, {}).get(normalized_key)
        if allowed_values is not None and value not in allowed_values:
            _record_diagnostic("invalid_enum")
            valid = False
            continue
        sanitized[normalized_key] = _sanitize_scalar(value)
    return (sanitized if valid or not reject_invalid else {}, valid)


def _sanitize_scalar(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str):
        return value
    redacted = _EMAIL_PATTERN.sub("[redacted-email]", value)
    redacted = _BEARER_PATTERN.sub("Bearer [redacted]", redacted)
    redacted = _QUERY_PATTERN.sub("?[redacted]", redacted)
    return _TOKEN_PATH_PATTERN.sub(r"\1[redacted]", redacted)


def emit_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int | None = None,
    fields: Mapping[str, object] | None = None,
    event_id: str | UUID | None = None,
    occurred_at: datetime | None = None,
) -> None:
    definition = _EVENT_CATALOG.get(event)
    if definition is None:
        _record_diagnostic("unknown_event")
        return
    occurrence_id = event_id or uuid4()
    if not isinstance(occurrence_id, (str, UUID)) or (
        isinstance(occurrence_id, str)
        and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,127}", occurrence_id)
    ):
        _record_diagnostic("invalid_envelope")
        return
    if occurred_at is not None and (
        not isinstance(occurred_at, datetime) or occurred_at.tzinfo is None
    ):
        _record_diagnostic("invalid_envelope")
        return
    occurrence_time = (occurred_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    reserved_fields = {
        "event_id",
        "schema_version",
        "occurred_at",
        "service",
        "environment",
        "request_id",
        "trace_id",
        "span_id",
    }
    for key, value in (fields or {}).items():
        if key in reserved_fields or (
            key == "outcome" and event != "admin.activity"
            and value != definition.default_outcome
        ):
            _record_diagnostic("invalid_envelope")
            return
    event_fields = {
        "schema_version": 1,
        "event_id": occurrence_id,
        "occurred_at": occurrence_time,
        "service": "kvarteret-personal",
        "environment": os.getenv("VERCEL_ENV") or os.getenv("APP_ENV", "unknown"),
        "outcome": definition.default_outcome,
        **current_trace_fields(),
        **{
            key: value
            for key, value in (fields or {}).items()
            if key not in reserved_fields
        },
    }
    sanitized, valid = _sanitize_fields(event, event_fields, reject_invalid=True)
    if not valid or "event_id" not in sanitized or "occurred_at" not in sanitized:
        _record_diagnostic("invalid_envelope")
        return
    try:
        logger.log(
            # Severity belongs to the catalog. Keep the parameter for source
            # compatibility while preventing call sites from overriding policy.
            definition.level,
            definition.message,
            extra={"event": event, "event_data": sanitized},
            stacklevel=3 if isinstance(logger, logging.Logger) else 2,
        )
    except Exception:
        _record_diagnostic("sink_failure")


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = str(getattr(record, "event", "log.message"))
        event_data = getattr(record, "event_data", None)
        if not isinstance(event_data, dict):
            event_data = {}
        occurrence = getattr(record, "_observability_occurrence", None)
        if not isinstance(occurrence, dict):
            occurrence = {
                "event_id": uuid4().hex,
                "occurred_at": datetime.now(UTC).isoformat(),
            }
            record._observability_occurrence = occurrence
        definition = _EVENT_CATALOG.get(event)
        safe_event_data = sanitize_fields(event, event_data)
        payload: dict[str, Any] = {
            "timestamp": occurrence["occurred_at"],
            "level": record.levelname,
            "logger": record.name,
            "event": event,
            "schema_version": 1,
            "event_id": safe_event_data.get("event_id") or occurrence["event_id"],
            "occurred_at": safe_event_data.get("occurred_at")
            or occurrence["occurred_at"],
            "service": "kvarteret-personal",
            "environment": os.getenv("VERCEL_ENV") or os.getenv("APP_ENV", "unknown"),
            "outcome": safe_event_data.get(
                "outcome", definition.default_outcome if definition else "success"
            ),
            # Free-form log messages can contain names, response bodies, or other
            # identifiers that pattern redaction cannot reliably recognize.
            # Export the stable event name and require useful diagnostics to use
            # the allowlisted structured fields below.
            "message": definition.message if definition else event,
        }
        payload.update(sanitize_fields(event, _request_context.get({})))
        reserved = {
            "event_id",
            "schema_version",
            "occurred_at",
            "service",
            "environment",
        }
        payload.update(
            {
                key: value
                for key, value in safe_event_data.items()
                if key not in reserved
            }
        )
        payload.update(
            {
                key: value
                for key, value in current_trace_fields().items()
                if key not in payload
            }
        )
        if record.exc_info:
            payload["error_category"] = record.exc_info[0].__name__.lower()
        return json.dumps(payload, default=str, ensure_ascii=True)


class IsolatedLoggingHandler(logging.Handler):
    """Prevent one sink failure from aborting logging or later sinks."""

    def __init__(self, delegate: logging.Handler) -> None:
        super().__init__(delegate.level)
        self.delegate = delegate

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.delegate.handle(record)
        except Exception:
            _record_diagnostic("sink_failure")


def _record_diagnostic(kind: str) -> None:
    if (
        kind not in _diagnostic_counters
        and len(_diagnostic_counters) >= _MAX_DIAGNOSTIC_COUNTER_KEYS
    ):
        kind = "other"
    _diagnostic_counters[kind] += 1
    try:
        _diagnostic_metric.add(1, {"reason": kind})
    except Exception:
        pass


def diagnostic_counts() -> dict[str, int]:
    return dict(_diagnostic_counters)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(IsolatedLoggingHandler(handler))
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    for logger_name, level in _NOISY_LOGGER_LEVELS.items():
        logging.getLogger(logger_name).setLevel(level)


def bind_request_context(**values: Any):
    current = dict(_request_context.get({}))
    current.update(sanitize_fields("http.request.completed", values))
    return _request_context.set(current)


def reset_request_context(token) -> None:
    _request_context.reset(token)


def clear_request_context() -> None:
    _request_context.set({})


def build_request_id(request: Request) -> str:
    candidate = request.headers.get("x-request-id", "").strip()
    if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", candidate):
        return candidate
    return uuid4().hex


def client_ip_from_request(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


def request_context_for_user(user: AuthenticatedUser | None) -> dict[str, Any]:
    if user is None:
        return {}
    return {"user_account_id": user.user_account_id}


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str):
        return path
    return "unmatched"


def log_request(
    logger: logging.Logger, *, request: Request, status_code: int, started_at: float
) -> None:
    # Healthy HTTP completions belong in request metrics and sampled spans.
    # Keep only server failures in the application log stream.
    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    try:
        _request_duration.record(duration_ms, {
            "http.request.method": request.method,
            "http.route": _route_template(request),
            "http.response.status_code": status_code,
        })
    except Exception:
        _record_diagnostic("metric_failure")
    if duration_ms >= 2_000:
        emit_event(
            logger,
            "http.request.slow",
            fields={
                "status_code": status_code,
                "duration_ms": duration_ms,
                "http_method": request.method,
                "route_template": _route_template(request),
            },
        )
    if status_code >= 500:
        emit_event(
            logger,
            "http.request.failed",
            fields={
                "status_code": status_code,
                "duration_ms": duration_ms,
                "http_method": request.method,
                "route_template": _route_template(request),
                "outcome": "failure",
            },
        )


def log_request_exception(
    logger: logging.Logger, *, request: Request, started_at: float
) -> None:
    # Keep the active exception attached so the error-tracking handler can
    # capture the stack while the formatter still exports only catalog fields.
    logger.exception(
        _EVENT_CATALOG["http.request.failed"].message,
        extra={
            "event": "http.request.failed",
            "event_data": {
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                "http_method": request.method,
                "route_template": _route_template(request),
                "outcome": "failure",
            },
        },
    )


def log_admin_activity(
    *,
    request: Request,
    user: AuthenticatedUser,
    action: str,
    outcome: str = "success",
    subject_type: str | None = None,
    subject_id: str | int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    safe_details = dict(details or {})
    if "setup_url" in safe_details:
        safe_details["setup_url_created"] = bool(safe_details.pop("setup_url"))
    emit_event(
        logging.getLogger("app.audit"),
        "admin.activity",
        fields={
            "action": action,
            "outcome": outcome,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "route_template": _route_template(request),
            "admin_user_account_id": user.user_account_id,
            "admin_role": user.role.value,
            **safe_details,
        },
    )


def redact_query_string(request: Request) -> str:
    # Kept for call-site compatibility. Query values are never exported.
    return "[redacted]" if request.query_params else ""


def log_operation_timing(
    logger: logging.Logger,
    *,
    operation: str,
    started_at: float,
    details: dict[str, Any] | None = None,
) -> None:
    try:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        _operation_duration.record(duration_ms, {"operation": operation})
        fields = {
            "operation": operation,
            "duration_ms": duration_ms,
            **(details or {}),
        }
        safe_fields = sanitize_fields("app.operation.timing", fields)
        safe_fields = {
            key: value for key, value in safe_fields.items() if value is not None
        }
        span = trace.get_current_span()
        if span.is_recording():
            span.add_event("app.operation.timing", attributes=safe_fields)
    except Exception:
        _record_diagnostic("span_failure")


_tracer = trace.get_tracer("kvarteret-personal")


@contextmanager
def with_named_span(name: str, attributes: Mapping[str, object] | None = None):
    """Run the wrapped block inside a named business-domain span.

    The span records ERROR status when the block raises. When telemetry is
    disabled the tracer yields a non-recording span and all calls are no-ops,
    so this helper is safe to use unconditionally.
    """
    with _tracer.start_as_current_span(name) as span:
        for key, value in (attributes or {}).items():
            span.set_attribute(key, value)
        try:
            yield span
        except BaseException:
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise
