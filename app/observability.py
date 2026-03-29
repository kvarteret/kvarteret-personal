from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import Request

from app.auth.models import AuthenticatedUser
from app.config import Settings

_request_context: ContextVar[dict[str, Any]] = ContextVar("request_context", default={})


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
                "query_string": request.url.query,
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
                "query_string": request.url.query,
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
                "query_string": request.url.query,
                "admin_user_account_id": user.user_account_id,
                "admin_auth_user_id": str(user.auth_user_id),
                "admin_username": user.username,
                "admin_role": user.role.value,
                "client_ip": client_ip_from_request(request),
                **(details or {}),
            },
        },
    )


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
