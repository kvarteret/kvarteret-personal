from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.observability import (
    JsonLogFormatter,
    sanitize_fields,
    with_named_span,
)
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


def test_prospect_conflict_allowlist_keeps_related_ids_only() -> None:
    fields = sanitize_fields(
        "volunteer.prospect.conflict",
        {
            "conflict_type": "existing_volunteer",
            "volunteer_id": 10232,
            "registration_id": 77,
            "email": "sentinel@example.com",
            "detail": "sentinel@example.com",
        },
    )

    assert fields == {
        "conflict_type": "existing_volunteer",
        "volunteer_id": 10232,
        "registration_id": 77,
    }


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


@pytest.fixture(scope="module", autouse=True)
def _global_trace_provider() -> Iterator[InMemorySpanExporter]:
    """Install a single global TracerProvider for this module.

    The OpenTelemetry SDK forbids overriding the global TracerProvider once
    set, so one provider with an in-memory exporter is installed for all tests
    in this module; each test clears the exporter before asserting.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    yield exporter
    exporter.shutdown()


def test_with_named_span_records_named_span_and_attributes(
    _global_trace_provider: InMemorySpanExporter,
) -> None:
    exporter = _global_trace_provider
    exporter.clear()
    with with_named_span("volunteer.prospect.register", {"registration_id": 7}):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "volunteer.prospect.register"
    assert span.attributes["registration_id"] == 7


def test_with_named_span_marks_error_status_on_exception(
    _global_trace_provider: InMemorySpanExporter,
) -> None:
    exporter = _global_trace_provider
    exporter.clear()
    with pytest.raises(RuntimeError, match="boom"):
        with with_named_span("feedback.submit"):
            raise RuntimeError("boom")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "feedback.submit"
    assert spans[0].status.status_code == trace.StatusCode.ERROR


def test_fastapi_instrumentation_joins_incoming_traceparent() -> None:
    """A server span must adopt the trace_id of an incoming W3C traceparent.

    This is the join point for web-injected trace context: when
    samfunnetibergen sends a request with the traceparent header, the
    kvarteret-personal HTTP span must land in the same trace.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    app = FastAPI()

    @app.get("/hello")
    async def hello() -> dict[str, str]:
        return {"ok": "true"}

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    client = TestClient(app)
    incoming_trace_id = 0x4BF92F3577B34DA6A3CE929D0E0E4736
    client.get(
        "/hello",
        headers={
            "traceparent": (
                "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
            )
        },
    )

    spans = exporter.get_finished_spans()
    server_spans = [span for span in spans if span.name == "GET /hello"]
    assert len(server_spans) == 1
    server_span = server_spans[0]
    assert server_span.get_span_context().trace_id == incoming_trace_id
    # The server span's parent must be the span advertised in the incoming
    # traceparent header (00f067aa0ba902b7), proving the join.
    assert server_span.parent is not None
    assert server_span.parent.span_id == 0x00F067AA0BA902B7
