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
    assert not spans[0].events  # raw exception messages must not leak via spans


def test_session_context_connects_failed_requests_and_otel_spans(caplog):
    from types import SimpleNamespace
    from app.config import Settings
    from app.main import _install_request_context_middleware
    from app.web.csrf import CSRF_COOKIE_NAME, CsrfTokenService

    settings = Settings(_env_file=None, app_env="test", app_secret_key="test-key")
    cookie = CsrfTokenService(settings).issue_token()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    app = FastAPI()
    app.state.container = SimpleNamespace(settings=settings)
    _install_request_context_middleware(app)

    @app.get("/failed")
    def failed():
        from fastapi.responses import Response

        return Response(status_code=403)

    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=provider, exclude_spans=["send", "receive"]
    )
    client = TestClient(app)
    client.cookies.set(CSRF_COOKIE_NAME, cookie)
    with caplog.at_level(logging.WARNING):
        responses = [client.get("/failed") for _ in range(2)]
    records = [
        json.loads(JsonLogFormatter().format(r))
        for r in caplog.records
        if getattr(r, "event", None) == "http.request.failed"
    ]
    spans = exporter.get_finished_spans()
    assert len(spans) == len(records) == 2
    assert records[0]["session_id"] == records[1]["session_id"]
    assert records[0]["trace_id"] != records[1]["trace_id"]
    for record, response, span in zip(records, responses, spans):
        assert record["request_id"] == response.headers["X-Request-ID"]
        assert record["schema_version"] == 1
        assert record["domain"] == "http"
        assert record["session_id"] == span.attributes["session.id"]
        assert record["trace_id"] == format(span.context.trace_id, "032x")
    assert cookie not in json.dumps(records)
    provider.shutdown()


def test_diagnostic_context_rejects_arbitrary_header_values():
    from starlette.requests import Request
    from app.config import Settings
    from app.observability import diagnostic_session_id, build_request_id

    settings = Settings(_env_file=None)
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"x-session-id", b"person@example.com"),
                (b"x-request-id", b"person@example.com"),
            ],
        }
    )
    assert len(diagnostic_session_id(request, settings)) == 32
    assert len(build_request_id(request)) == 32


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


def test_mobile_diagnostic_header_takes_precedence_over_browser_cookie() -> None:
    from fastapi import Request
    from itsdangerous import URLSafeSerializer
    from app.config import Settings
    from app.observability import diagnostic_session_id

    settings = Settings(_env_file=None)
    cookie = URLSafeSerializer(settings.app_secret_key, salt="kvarteret-csrf").dumps(
        {"nonce": "browser"}
    )
    supplied = "a" * 32
    request = Request(
        {
            "type": "http",
            "path": "/api/v1/mobile-card/me",
            "headers": [
                (b"cookie", f"kvarteret_csrf={cookie}".encode()),
                (b"x-session-id", supplied.encode()),
            ],
        }
    )
    assert diagnostic_session_id(request, settings) == supplied


def test_invalid_mobile_token_retains_safe_failure_reason(caplog) -> None:
    from app.config import Settings
    from app.domain.mobile_card.sessions import MobileCardSessionManager
    from app.domain.mobile_card.errors import MobileCardInvalidSessionError

    with caplog.at_level(logging.WARNING), pytest.raises(MobileCardInvalidSessionError):
        MobileCardSessionManager(Settings(_env_file=None)).decode_token(
            "sentinel-invalid-token"
        )
    record = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "mobile_card.session.invalid"
    )
    assert record.event_data == {"reason": "bad_signature"}
    assert "sentinel-invalid-token" not in record.getMessage()
