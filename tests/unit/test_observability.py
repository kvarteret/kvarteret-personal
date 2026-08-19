from __future__ import annotations

import json
import logging
import sys
from typing import Any, cast

from opentelemetry.sdk.resources import Resource

from app.observability import JsonLogFormatter, sanitize_fields
from app.telemetry import (
    _SanitizedLoggingHandler,
    _TRACE_SAMPLE_RATE,
    _build_trace_provider,
)


def test_trace_sample_rate_is_ten_percent() -> None:
    provider = _build_trace_provider(Resource.create({}))

    assert _TRACE_SAMPLE_RATE == 0.1
    assert "root:TraceIdRatioBased{0.1}" in provider.sampler.get_description()
    provider.shutdown()


def test_allowlist_and_redaction_drop_sentinel_pii() -> None:
    fields = sanitize_fields(
        "email.delivery",
        {
            "email_delivery_id": "01234567-89ab-cdef-0123-456789abcdef",
            "registration_id": 42,
            "error_category": "failed for sentinel@example.com?token=secret",
            "recipient_email": "sentinel@example.com",
            "unknown": {"password": "secret"},
        },
    )

    serialized = json.dumps(fields)
    assert fields["registration_id"] == 42
    assert "recipient_email" not in fields
    assert "unknown" not in fields
    assert "sentinel@example.com" not in serialized
    assert "token=secret" not in serialized


def test_client_error_allowlist_keeps_only_declared_fields_and_redacts() -> None:
    fields = sanitize_fields(
        "web.client_error",
        {
            "error_type": "uncaught",
            "error_text": "boom for sentinel@example.com?token=secret",
            "error_source": "/courses/4?token=secret",
            "user_agent": "secret-agent",
            "arbitrary": "drop me",
        },
    )

    serialized = json.dumps(fields)
    assert fields["error_type"] == "uncaught"
    assert "user_agent" not in fields
    assert "arbitrary" not in fields
    assert "sentinel@example.com" not in serialized
    assert "token=secret" not in serialized
    assert "error_source" in fields


def test_json_formatter_does_not_export_exception_text() -> None:
    try:
        raise ValueError("sentinel@example.com Bearer top-secret")
    except ValueError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="app.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="request failed for sentinel@example.com/apply/sentinel-token",
        args=(),
        exc_info=exc_info,
    )
    payload = json.loads(JsonLogFormatter().format(record))

    serialized = json.dumps(payload)
    assert payload["error_category"] == "valueerror"
    assert "sentinel@example.com" not in serialized
    assert "top-secret" not in serialized
    assert "sentinel-token" not in serialized


def test_json_formatter_does_not_export_unstructured_message_values() -> None:
    record = logging.LogRecord(
        name="app.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Failure for Sentinel Person at +47 999 99 999: private response body",
        args=(),
        exc_info=None,
    )

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["event"] == "log.message"
    assert payload["message"] == "log.message"
    assert "Sentinel Person" not in json.dumps(payload)
    assert "999 99 999" not in json.dumps(payload)


def test_otlp_handler_exports_only_sanitized_record() -> None:
    emitted = []

    class CapturingLogger:
        def emit(self, record) -> None:
            emitted.append(record)

    class CapturingProvider:
        def get_logger(self, *args, **kwargs):
            return CapturingLogger()

    try:
        raise RuntimeError("sentinel@example.com Bearer top-secret")
    except RuntimeError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="app.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="failed for sentinel@example.com",
        args=(),
        exc_info=exc_info,
    )
    record.event = "email.delivery"
    record.event_data = {
        "registration_id": 42,
        "recipient_email": "sentinel@example.com",
    }
    handler = _SanitizedLoggingHandler(
        logger_provider=cast(Any, CapturingProvider())
    )

    handler.emit(record)

    assert len(emitted) == 1
    exported = emitted[0]
    serialized = json.dumps(
        {"body": exported.body, "attributes": dict(exported.attributes)}
    )
    assert "sentinel@example.com" not in serialized
    assert "top-secret" not in serialized
    assert "event_data" not in exported.attributes
    assert "exception.message" not in exported.attributes
    assert "exception.stacktrace" not in exported.attributes
