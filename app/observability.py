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
from app.exception_diagnostics import exception_diagnostics

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
    "uvicorn.access": logging.WARNING,
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
        "error_chain",
        "db_sqlstate",
        "retryable",
        "delivery_uncertain",
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
    "auth.login.failed": frozenset({"reason"}),
    "auth.login.succeeded": frozenset({"role"}),
    "volunteer.prospect.auth.rejected": frozenset({"reason"}),
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
    "mobile_card.access_code.sent": frozenset({"subject_type", "subject_id"}),
    "mobile_card.session.created": frozenset({"subject_type", "subject_id"}),
    "mobile_card.session.renewed": frozenset(
        {
            "age_seconds",
            "is_review",
            "remaining_seconds",
            "ttl_seconds",
            "renewal_threshold_seconds",
        }
    ),
    "mobile_card.session.invalid": frozenset({"reason"}),
    "mobile_card.client_session_logout": frozenset(
        {
            "event_name",
            "platform",
            "app_version",
            "auth_error_code",
            "auth_error_status",
            "had_cached_user",
            "had_login_marker",
            "had_stored_credentials",
        }
    ),
    "feedback.issue.created": frozenset({"feedback_source", "issue_identifier"}),
    "volunteer.prospect.conflict": frozenset({"conflict_type"}),
    "volunteer.prospect.validation_failed": frozenset(
        {"validation_codes", "validation_fields", "validation_issue_count"}
    ),
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
        # These explicitly declared fields contain an ID/boolean, not an email
        # address or URL. Keep them usable for domain-event correlation.
        if normalized_key == "setup_url_created" and not isinstance(value, bool):
            continue
        if normalized_key not in {"email_delivery_id", "setup_url_created"} and any(
            part in normalized_key.lower() for part in _FORBIDDEN_KEY_PARTS
        ):
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


_ADMIN_DIAGNOSTIC_ACTIONS = frozenset(
    {
        "volunteer_application.list",
        "volunteer_application.view",
        "email_delivery.list",
        "email_delivery.view",
        "admin_account.list",
        "admin_account.view_detail",
        "volunteer.view_detail",
        "search.volunteers",
        "group.preview_semester_transfer",
        "spotify.now_playing.view",
        "spotify.oauth.login.start",
    }
)


def emit_committed_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    fields: Mapping[str, object] | None = None,
) -> None:
    """Announce database outcomes only after the active transaction commits."""
    from sqlalchemy import event as sqlalchemy_event
    from app.db.session import current_session

    session = current_session()
    if session is None or not session.in_transaction():
        emit_event(logger, event, level=level, fields=fields)
        return
    sync_session = session.sync_session
    key = "observability.committed_events"
    if key not in sync_session.info:
        sync_session.info[key] = []

        def committed(session):
            if session.in_nested_transaction():
                return
            pending, session.info[key] = session.info[key], []
            for event_logger, name, severity, data, transaction in pending:
                emit_event(event_logger, name, level=severity, fields=data)

        def rolled_back(session, previous_transaction):
            def belongs_to_rollback(item):
                transaction = item[-1]
                while transaction is not None:
                    if transaction is previous_transaction:
                        return True
                    transaction = transaction.parent
                return False

            session.info[key] = [
                item for item in session.info[key] if not belongs_to_rollback(item)
            ]

        def ended(session, transaction):
            # Session.close() ends an uncommitted transaction without invoking
            # after_rollback. Never carry its events into a reused session.
            if transaction.parent is None:
                session.info[key].clear()

        sqlalchemy_event.listen(sync_session, "after_commit", committed)
        sqlalchemy_event.listen(sync_session, "after_soft_rollback", rolled_back)
        sqlalchemy_event.listen(sync_session, "after_transaction_end", ended)
    sync_session.info[key].append(
        (
            logger,
            event,
            level,
            sanitize_fields(
                event,
                {
                    **_request_context.get({}),
                    **current_trace_fields(),
                    **(fields or {}),
                },
            ),
            sync_session.get_nested_transaction() or sync_session.get_transaction(),
        )
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
            payload.update(
                sanitize_fields(event, exception_diagnostics(record.exc_info[1]))
            )
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
    # Request traces carry routine traffic. Keep a fallback for handled server
    # failures; expected client rejections have their own domain diagnostics.
    emit_event(
        logger,
        "http.request.failed" if status_code >= 500 else "http.request.completed",
        level=logging.ERROR if status_code >= 500 else logging.DEBUG,
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
    # Reads and OAuth initiation are diagnostics, not business changes.
    diagnostic = action in _ADMIN_DIAGNOSTIC_ACTIONS
    emitter = emit_event if diagnostic or outcome != "success" else emit_committed_event
    emitter(
        logging.getLogger("app.audit"),
        "admin.activity",
        level=logging.DEBUG
        if diagnostic
        else logging.WARNING
        if outcome != "success"
        else logging.INFO,
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
        level=logging.DEBUG,
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
