from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from time import perf_counter
from typing import Any, cast

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.observability import (
    IsolatedLoggingHandler,
    JsonLogFormatter,
    build_request_id,
    diagnostic_counts,
    emit_event,
    get_domain_logger,
    log_operation_timing,
    sanitize_fields,
    with_named_span,
)
from app.telemetry import (
    _SanitizedLoggingHandler,
    _build_trace_provider,
)


@pytest.mark.parametrize("parent_sampled", [None, False, True])
def test_all_valid_traces_are_recorded(parent_sampled) -> None:
    provider = _build_trace_provider(Resource.create({}))
    parent = None
    if parent_sampled is not None:
        parent = trace.set_span_in_context(
            trace.NonRecordingSpan(
                trace.SpanContext(
                    trace_id=1,
                    span_id=2,
                    is_remote=True,
                    trace_flags=trace.TraceFlags(1 if parent_sampled else 0),
                )
            )
        )
    with provider.get_tracer(__name__).start_as_current_span(
        "request", context=parent
    ) as span:
        assert span.is_recording()
        assert span.get_span_context().trace_flags.sampled
        if parent is not None:
            assert span.get_span_context().trace_id == 1
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
    assert fields["email_delivery_id"] == "01234567-89ab-cdef-0123-456789abcdef"
    assert fields["registration_id"] == 42
    assert "recipient_email" not in fields
    assert "unknown" not in fields
    assert "sentinel@example.com" not in serialized
    assert "token=secret" not in serialized


def test_request_id_accepts_bounded_client_correlation_and_replaces_invalid_values() -> (
    None
):
    valid_request = Request(
        {
            "type": "http",
            "headers": [(b"x-request-id", b"mobile-card:request-1")],
            "method": "POST",
            "path": "/api/v1/mobile-card/sessions",
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    invalid_request = Request(
        {
            "type": "http",
            "headers": [(b"x-request-id", b"bad value with spaces")],
            "method": "POST",
            "path": "/api/v1/mobile-card/sessions",
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )

    assert build_request_id(valid_request) == "mobile-card:request-1"
    generated_id = build_request_id(invalid_request)
    assert len(generated_id) == 32
    assert generated_id.isalnum()


def test_emit_event_uses_catalog_message_and_occurrence_envelope(caplog) -> None:
    logger = logging.getLogger("app.test.catalog")

    with caplog.at_level(logging.INFO, logger=logger.name):
        from app.observability import emit_event

        emit_event(
            logger,
            "email.delivery.queued",
            fields={"email_delivery_id": "delivery-1"},
            event_id="occurrence-1",
        )

    record = caplog.records[-1]
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["message"] == "Email delivery queued"
    assert payload["event_id"] == "occurrence-1"
    assert payload["schema_version"] == 1
    assert payload["email_delivery_id"] == "delivery-1"


def test_domain_logger_accepts_typed_keyword_fields(caplog) -> None:
    logger = get_domain_logger("app.test.adapter")

    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.event("auth.login.failed", reason_code="account_not_found")

    assert caplog.records[-1].event_data["reason_code"] == "account_not_found"


def test_invalid_event_fields_drop_the_whole_event(caplog) -> None:
    before = diagnostic_counts().get("invalid_envelope", 0)

    with caplog.at_level(logging.INFO, logger="app.test.invalid"):
        emit_event(
            logging.getLogger("app.test.invalid"),
            "auth.login.failed",
            fields={"reason_code": "unexpected free text"},
        )

    assert not caplog.records
    assert diagnostic_counts().get("invalid_envelope", 0) > before


def test_json_formatter_preserves_occurrence_identity_across_projections() -> None:
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="ignored",
        args=(),
        exc_info=None,
    )
    record.event = "email.delivery.queued"
    record.event_data = {
        "event_id": "occurrence-1",
        "occurred_at": "2026-09-10T12:00:00+00:00",
    }

    first = json.loads(JsonLogFormatter().format(record))
    second = json.loads(JsonLogFormatter().format(record))

    assert first["event_id"] == second["event_id"] == "occurrence-1"
    assert first["occurred_at"] == second["occurred_at"]
    assert first["timestamp"] == second["timestamp"]


def test_json_formatter_does_not_allow_null_occurrence_fields() -> None:
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="ignored",
        args=(),
        exc_info=None,
    )
    record.event = "email.delivery.queued"
    record.event_data = {"event_id": None, "occurred_at": None}

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["event_id"]
    assert payload["occurred_at"]


def test_operation_timing_is_preserved_as_a_span_event(
    _global_trace_provider: InMemorySpanExporter,
) -> None:
    exporter = _global_trace_provider
    exporter.clear()
    with with_named_span("app.operation"):
        log_operation_timing(
            logging.getLogger("app.performance"),
            operation="volunteers.detail.shell",
            started_at=perf_counter(),
            details={"volunteer_id": 7},
        )

    span = exporter.get_finished_spans()[0]
    assert span.events[0].name == "app.operation.timing"
    assert span.events[0].attributes["operation"] == "volunteers.detail.shell"
    assert span.events[0].attributes["volunteer_id"] == 7


def test_isolated_logging_handler_allows_later_sink_to_receive_record() -> None:
    class FailingHandler(logging.Handler):
        def emit(self, record) -> None:
            raise RuntimeError("sink unavailable")

    received: list[logging.LogRecord] = []

    class CapturingHandler(logging.Handler):
        def emit(self, record) -> None:
            received.append(record)

    logger = logging.getLogger("app.test.isolated")
    logger.handlers.clear()
    old_level = logger.level
    old_propagate = logger.propagate
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(IsolatedLoggingHandler(FailingHandler()))
    logger.addHandler(IsolatedLoggingHandler(CapturingHandler()))
    try:
        logger.info("event")
    finally:
        logger.handlers.clear()
        logger.setLevel(old_level)
        logger.propagate = old_propagate

    assert len(received) == 1


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
    handler = _SanitizedLoggingHandler(logger_provider=cast(Any, CapturingProvider()))

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
    assert exported.body == "email.delivery"
    assert exported.attributes["registration_id"] == 42
    assert exported.attributes["error_category"] == "runtimeerror"


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
            "traceparent": ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
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


def test_shared_contract_fixture_executes_for_personal(caplog):
    from pathlib import Path
    fixture = json.loads((Path(__file__).parents[1] / "fixtures/observability_contract.json").read_text())
    with caplog.at_level(logging.INFO):
        get_domain_logger("app.fixture").event("email.delivery.queued", email_delivery_id=fixture["allowed_delivery_id"])
    payload = json.loads(JsonLogFormatter().format(caplog.records[-1]))
    assert set(fixture["envelope"]) <= payload.keys()
    assert payload["schema_version"] == fixture["schema_version"]
    for sentinel in fixture["redaction_sentinels"]:
        safe = sanitize_fields("email.delivery.failed", {"error_category": sentinel})
        assert sentinel not in json.dumps(safe)
    for field in fixture["forbidden_fields"]:
        assert field not in sanitize_fields("email.delivery.queued", {field: "private"})


@pytest.mark.parametrize("fields", [
    {"registration_id": "private name"}, {"registration_id": True},
    {"registration_id": float("nan")}, {"outcome": "failure", "registration_id": 1},
    {"service": "forged", "registration_id": 1}, {},
])
def test_invalid_occurrence_cannot_override_catalog_or_omit_required_fields(fields, caplog):
    with caplog.at_level(logging.INFO):
        get_domain_logger("app.invalid").event("volunteer.application.approved", fields=fields)
    assert not caplog.records
