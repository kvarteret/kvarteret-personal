from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from opentelemetry import trace

from app.auth.models import AuthenticatedUser
from app.config import Settings

_request_context: ContextVar[dict[str, Any]] = ContextVar("request_context", default={})

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
        "service",
        "environment",
        "request_id",
        "trace_id",
        "span_id",
        "registration_id",
        "origin_trace_id",
        "volunteer_id",
        "email_delivery_id",
        "template_key",
        "status",
        "status_code",
        "outcome",
        "failure_stage",
        "error_category",
        "smtp_status_class",
        "attempt_no",
        "duration_ms",
        "http_method",
        "route_template",
        "user_account_id",
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
    "email.delivery": frozenset({"lease_owner"}),
    "volunteer.prospect.conflict": frozenset({"conflict_type"}),
    "web.client_error": frozenset(
        {
            "error_type",
            "error_text",
            "error_source",
            "form_id",
            "attempt_count",
            "validation_fields",
            "validation_codes",
        }
    ),
}

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


def _allowed_fields(event: str) -> frozenset[str]:
    return _COMMON_FIELDS | _EVENT_FIELDS.get(event, frozenset())


def sanitize_fields(event: str, values: Mapping[str, object]) -> dict[str, object]:
    allowed = _allowed_fields(event)
    sanitized: dict[str, object] = {}
    for key, value in values.items():
        normalized_key = key.strip()
        if normalized_key not in allowed or not _is_safe_scalar(value):
            continue
        if any(part in normalized_key.lower() for part in _FORBIDDEN_KEY_PARTS):
            continue
        sanitized[normalized_key] = _sanitize_scalar(value)
    return sanitized


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
    level: int = logging.INFO,
    fields: Mapping[str, object] | None = None,
) -> None:
    event_fields = {**current_trace_fields(), **(fields or {})}
    logger.log(
        level,
        event,
        extra={"event": event, "event_data": sanitize_fields(event, event_fields)},
    )


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = str(getattr(record, "event", "log.message"))
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": event,
            # Free-form log messages can contain names, response bodies, or other
            # identifiers that pattern redaction cannot reliably recognize.
            # Export the stable event name and require useful diagnostics to use
            # the allowlisted structured fields below.
            "message": event,
        }
        payload.update(sanitize_fields(event, _request_context.get({})))
        event_data = getattr(record, "event_data", None)
        if isinstance(event_data, dict):
            payload.update(sanitize_fields(event, event_data))
        payload.update(current_trace_fields())
        if record.exc_info:
            payload["error_category"] = record.exc_info[0].__name__.lower()
        return json.dumps(payload, default=str, ensure_ascii=True)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
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
    return request.headers.get("x-request-id") or uuid4().hex


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
    emit_event(
        logger,
        "http.request.completed",
        level=logging.ERROR
        if status_code >= 500
        else logging.WARNING
        if status_code >= 400
        else logging.INFO,
        fields={
            "status_code": status_code,
            "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            "http_method": request.method,
            "route_template": _route_template(request),
        },
    )


def log_request_exception(
    logger: logging.Logger, *, request: Request, started_at: float
) -> None:
    logger.exception(
        "http.request.failed",
        extra={
            "event": "http.request.failed",
            "event_data": {
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                "http_method": request.method,
                "route_template": _route_template(request),
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
    emit_event(
        logger,
        "app.operation.timing",
        fields={
            "operation": operation,
            "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            **(details or {}),
        },
    )


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
