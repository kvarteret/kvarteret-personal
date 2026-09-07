import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from posthog import Posthog
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.config import Settings
from app.error_tracking import ExceptionLoggingHandler, sanitize_exception_event
from app.main import _install_request_context_middleware
from app.telemetry import TelemetryFlushMiddleware, install_telemetry_flush


def test_exception_wire_payload_keeps_frames_without_private_values(monkeypatch):
    events = []

    def before_send(event):
        events.append(sanitize_exception_event(event))
        return None

    client = Posthog("test", send=False, sync_mode=True, before_send=before_send)
    handler = ExceptionLoggingHandler(client, Settings(_env_file=None, app_env="test"))
    log = logging.getLogger("app.test_error_tracking")
    monkeypatch.setattr(log, "handlers", [handler])
    monkeypatch.setattr(log, "propagate", False)
    try:
        private_local = "Sentinel Person password=private-secret"
        raise ValueError(private_local)
    except ValueError:
        log.exception("Private message: %s", private_local)

    assert len(events) == 1
    event = events[0]
    wire = json.dumps(event)
    assert "Sentinel" not in wire
    assert "private-secret" not in wire
    assert "pre_context" not in wire
    assert "context_line" not in wire
    exception = event["properties"]["$exception_list"][0]
    assert exception["type"] == "ValueError"
    assert (
        exception["stacktrace"]["frames"][-1]["function"]
        == "test_exception_wire_payload_keeps_frames_without_private_values"
    )
    assert event["properties"]["service"] == "kvarteret-personal"
    assert event["properties"]["$process_person_profile"] is False


@pytest.mark.parametrize("fails", [False, True])
def test_request_exception_captured_and_flush_runs_on_success_and_failure(
    monkeypatch, fails
):
    captures = []
    flushed = []

    class Client:
        def capture_exception(self, exception, **kwargs):
            captures.append((exception, kwargs))

    class Provider:
        def force_flush(self, **kwargs):
            flushed.append(True)
            raise RuntimeError("exporter down")

    log = logging.getLogger("app.main")
    monkeypatch.setattr(
        log,
        "handlers",
        [ExceptionLoggingHandler(Client(), Settings(_env_file=None, app_env="test"))],
    )
    monkeypatch.setattr(log, "propagate", False)
    app = FastAPI()
    _install_request_context_middleware(app)
    app.add_middleware(TelemetryFlushMiddleware, providers=(Provider(),))

    @app.get("/example/{item_id}")
    def example(item_id: str):
        if fails:
            raise ValueError("secret")
        return {"ok": True}

    response = TestClient(app, raise_server_exceptions=False).get(
        "/example/123?token=secret"
    )
    assert response.status_code == (500 if fails else 200)
    assert flushed == [True]
    assert len(captures) == int(fails)
    if fails:
        assert captures[0][0][0] is ValueError
        assert captures[0][1]["properties"]["route_template"] == "/example/{item_id}"


def test_exporter_errors_do_not_recurse():
    class Client:
        def capture_exception(self, *args, **kwargs):
            pytest.fail("must not capture SDK failures")

    handler = ExceptionLoggingHandler(Client(), Settings(_env_file=None))
    handler.emit(
        logging.LogRecord(
            "posthog",
            logging.ERROR,
            __file__,
            1,
            "failed",
            (),
            (RuntimeError, RuntimeError(), None),
        )
    )


def test_flush_includes_finished_server_span():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(
        BatchSpanProcessor(exporter, schedule_delay_millis=60000)
    )
    app = FastAPI()

    @app.get("/hello")
    def hello():
        return {"ok": True}

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    install_telemetry_flush(app, (provider,))
    assert TestClient(app).get("/hello").status_code == 200
    assert any(span.name == "GET /hello" for span in exporter.get_finished_spans())
    provider.shutdown()
