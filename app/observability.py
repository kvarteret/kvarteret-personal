from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import Request

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
}
_SENSITIVE_QUERY_KEYS = frozenset(
    {
        "code",
        "completion_error",
        "csrf_token",
        "error",
        "password",
        "password_error",
        "state",
        "token",
    }
)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_request_context.get())
        event = getattr(record, "event", None)
        if event is not None:
            payload["event"] = event
        event_data = getattr(record, "event_data", None)
        if isinstance(event_data, dict):
            payload.update(event_data)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
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
    current = dict(_request_context.get())
    for key, value in values.items():
        if value is None:
            continue
        current[key] = value
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
    return {
        "user_account_id": user.user_account_id,
        "auth_user_id": str(user.auth_user_id),
        "username": user.username,
        "user_role": user.role.value,
    }


def log_request(logger: logging.Logger, *, request: Request, status_code: int, started_at: float) -> None:
    logger.info(
        "request completed",
        extra={
            "event": "http.request.completed",
            "event_data": {
                "status_code": status_code,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                "query_string_redacted": redact_query_string(request),
            },
        },
    )


def log_request_exception(logger: logging.Logger, *, request: Request, started_at: float) -> None:
    logger.exception(
        "request failed",
        extra={
            "event": "http.request.failed",
            "event_data": {
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                "query_string_redacted": redact_query_string(request),
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
    logging.getLogger("app.audit").info(
        "admin activity",
        extra={
            "event": "admin.activity",
            "event_data": {
                "action": action,
                "outcome": outcome,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "path": request.url.path,
                "query_string_redacted": redact_query_string(request),
                "admin_user_account_id": user.user_account_id,
                "admin_auth_user_id": str(user.auth_user_id),
                "admin_username": user.username,
                "admin_role": user.role.value,
                "client_ip": client_ip_from_request(request),
                **(details or {}),
            },
        },
    )


def redact_query_string(request: Request) -> str:
    if not request.query_params:
        return ""
    sanitized_items: list[tuple[str, str]] = []
    for key, value in request.query_params.multi_items():
        sanitized_items.append(
            (
                key,
                "[redacted]" if key.strip().lower() in _SENSITIVE_QUERY_KEYS else value,
            )
        )
    return urlencode(sanitized_items, doseq=True)


def log_operation_timing(
    logger: logging.Logger,
    *,
    operation: str,
    started_at: float,
    details: dict[str, Any] | None = None,
) -> None:
    logger.info(
        "operation timing",
        extra={
            "event": "app.operation.timing",
            "event_data": {
                "operation": operation,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                **(details or {}),
            },
        },
    )
