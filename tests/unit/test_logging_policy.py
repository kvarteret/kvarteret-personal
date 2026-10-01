from __future__ import annotations

import logging
from time import perf_counter

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.db.session import reset_request_session, set_request_session
from app.observability import get_logger, log_operation_timing, log_request
from app.telemetry import DomainLogFilter


@pytest.mark.parametrize("status", [200, 202, 303, 400, 401, 404, 422, 429])
def test_routine_http_responses_are_debug_only(caplog, status):
    logger = get_logger("app.test")
    with caplog.at_level(logging.DEBUG):
        log_request(
            logger,
            request=Request({"type": "http", "method": "GET"}),
            status_code=status,
            started_at=perf_counter(),
        )
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.DEBUG
    assert not DomainLogFilter().filter(caplog.records[0])


def test_handled_server_failure_remains_searchable(caplog):
    with caplog.at_level(logging.DEBUG):
        log_request(
            get_logger("app.test"),
            request=Request({"type": "http", "method": "GET"}),
            status_code=503,
            started_at=perf_counter(),
        )
    assert caplog.records[0].event == "http.request.failed"
    assert caplog.records[0].event_data["status_code"] == 503
    assert DomainLogFilter().filter(caplog.records[0])


def test_operation_timing_is_debug_only(caplog):
    with caplog.at_level(logging.DEBUG):
        log_operation_timing(
            get_logger("app.performance"),
            operation="list_volunteers",
            started_at=perf_counter(),
        )
    assert caplog.records[0].levelno == logging.DEBUG
    assert not DomainLogFilter().filter(caplog.records[0])


@pytest.mark.parametrize(
    ("name", "level", "event", "expected"),
    [
        ("app.workflow", logging.INFO, "volunteer.lifecycle", True),
        ("app.workflow", logging.DEBUG, "volunteer.lifecycle", False),
        ("app.test", logging.INFO, None, False),
        ("httpx", logging.INFO, None, False),
        ("uvicorn.access", logging.INFO, None, False),
        ("httpx", logging.WARNING, None, True),
        ("app.test", logging.ERROR, None, True),
    ],
)
def test_export_policy(name, level, event, expected):
    record = logging.LogRecord(name, level, __file__, 1, "message", (), None)
    if event:
        record.event = event
    assert DomainLogFilter().filter(record) is expected


@pytest.mark.parametrize("commit", [True, False])
async def test_transaction_outcome_controls_domain_log(caplog, commit):
    async with AsyncSession() as session:
        token = set_request_session(session)
        try:
            await session.begin()
            with caplog.at_level(logging.INFO):
                get_logger("app.audit").info(
                    "admin.activity",
                    extra={"subject_id": 42, "action": "volunteer.delete"},
                    after_commit=True,
                )
                assert not caplog.records
                if commit:
                    await session.commit()
                else:
                    await session.rollback()
                assert len(caplog.records) == int(commit)
                if commit:
                    assert caplog.records[0].event_data["subject_id"] == 42
                # Reuse the same session: rolled-back events must not leak.
                await session.begin()
                await session.commit()
                assert len(caplog.records) == int(commit)
        finally:
            reset_request_session(token)


async def test_savepoint_does_not_announce_outer_transaction(caplog):
    async with AsyncSession() as session:
        token = set_request_session(session)
        try:
            await session.begin()
            with caplog.at_level(logging.INFO):
                get_logger("app.audit").info("admin.activity", after_commit=True)
                async with session.begin_nested():
                    pass
                assert not caplog.records
                await session.rollback()
                assert not caplog.records
        finally:
            reset_request_session(token)


async def test_savepoint_rollback_discards_only_its_events(caplog):
    async with AsyncSession() as session:
        token = set_request_session(session)
        try:
            await session.begin()
            with caplog.at_level(logging.INFO):
                get_logger("app.audit").info(
                    "admin.activity", extra={"subject_id": 1}, after_commit=True
                )
                nested = await session.begin_nested()
                get_logger("app.audit").info(
                    "admin.activity", extra={"subject_id": 2}, after_commit=True
                )
                await nested.rollback()
                assert not caplog.records
                await session.commit()
                assert [r.event_data["subject_id"] for r in caplog.records] == [1]
        finally:
            reset_request_session(token)


@pytest.mark.parametrize(
    ("action", "outcome", "level"),
    [
        ("volunteer_application.list", "success", logging.DEBUG),
        ("search.volunteers", "success", logging.DEBUG),
        ("spotify.oauth.login.start", "success", logging.DEBUG),
        ("volunteer.delete", "success", logging.INFO),
        ("volunteer.delete", "failure", logging.WARNING),
    ],
)
def test_admin_reads_are_diagnostics_and_mutations_are_outcomes(
    caplog, action, outcome, level
):
    from types import SimpleNamespace

    from app.observability import log_admin_activity

    with caplog.at_level(logging.DEBUG):
        log_admin_activity(
            request=Request({"type": "http", "method": "GET"}),
            user=SimpleNamespace(
                user_account_id=1, role=SimpleNamespace(value="admin")
            ),
            action=action,
            outcome=outcome,
        )
    assert caplog.records[0].levelno == level
    assert caplog.records[0].event_data["outcome"] == outcome
    assert (
        caplog.records[0].funcName
        == "test_admin_reads_are_diagnostics_and_mutations_are_outcomes"
    )


async def test_closed_transaction_does_not_leak_into_reused_session(caplog):
    async with AsyncSession() as session:
        token = set_request_session(session)
        try:
            with caplog.at_level(logging.INFO):
                await session.begin()
                get_logger("app.audit").info("admin.activity", after_commit=True)
                await session.close()
                await session.begin()
                await session.commit()
                assert not caplog.records
        finally:
            reset_request_session(token)


def test_safe_email_delivery_id_and_url_presence_remain_filterable():
    from app.observability import sanitize_fields

    assert sanitize_fields(
        "email.delivery",
        {
            "email_delivery_id": "12345678-1234-1234-1234-123456789012",
            "recipient_email": "private@example.com",
        },
    ) == {"email_delivery_id": "12345678-1234-1234-1234-123456789012"}
    assert sanitize_fields(
        "admin.activity",
        {
            "setup_url_created": True,
            "setup_url": "https://example.com/set-password/secret",
        },
    ) == {"setup_url_created": True}
    assert (
        sanitize_fields(
            "admin.activity",
            {
                "setup_url_created": "https://example.com/set-password/secret",
            },
        )
        == {}
    )


def test_adapter_captures_request_route_trace_and_caller(caplog):
    import json
    from types import SimpleNamespace

    from opentelemetry.sdk.trace import TracerProvider

    from app.observability import (
        JsonLogFormatter,
        bind_request_context,
        reset_request_context,
    )

    request = Request({"type": "http", "method": "POST"})
    token = bind_request_context(
        request=request, request_id="request-42", http_method="POST"
    )
    provider = TracerProvider()
    try:
        # Routing happens after the middleware binds context.
        request.scope["route"] = SimpleNamespace(path="/feedback/{source}")
        with provider.get_tracer(__name__).start_as_current_span("feedback") as span:
            context = span.get_span_context()
            with caplog.at_level(logging.INFO):
                get_logger("app.feedback").info(
                    "feedback.issue.created",
                    extra={"issue_identifier": "IT-42", "email": "private@example.com"},
                )
        record = caplog.records[0]
    finally:
        reset_request_context(token)
        provider.shutdown()
    # Formatting happens with no original request/span active.
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["event"] == "feedback.issue.created"
    assert payload["issue_identifier"] == "IT-42"
    assert payload["request_id"] == "request-42"
    assert payload["http_method"] == "POST"
    assert payload["route_template"] == "/feedback/{source}"
    assert payload["trace_id"] == format(context.trace_id, "032x")
    assert payload["span_id"] == format(context.span_id, "016x")
    assert (
        payload["code.function"]
        == "test_adapter_captures_request_route_trace_and_caller"
    )
    assert payload["code.filepath"] == __file__
    assert "email" not in payload
    assert len(caplog.records) == 1


async def test_committed_record_preserves_original_trace_in_otlp(caplog):
    from typing import Any, cast

    from opentelemetry.sdk.trace import TracerProvider

    from app.observability import bind_request_context, reset_request_context
    from app.telemetry import _SanitizedLoggingHandler

    emitted = []

    class CapturingLogger:
        def emit(self, record):
            emitted.append(record)

    class CapturingProvider:
        def get_logger(self, *args, **kwargs):
            return CapturingLogger()

    provider = TracerProvider()
    tracer = provider.get_tracer(__name__)
    async with AsyncSession() as session:
        session_token = set_request_session(session)
        request_token = bind_request_context(request_id="original-request")
        try:
            await session.begin()
            with caplog.at_level(logging.INFO):
                with tracer.start_as_current_span("original") as span:
                    original_context = span.get_span_context()
                    get_logger("app.audit").info(
                        "admin.activity", extra={"subject_id": 42}, after_commit=True
                    )
                reset_request_context(request_token)
                request_token = bind_request_context(request_id="another-request")
                with tracer.start_as_current_span("commit"):
                    await session.commit()
                    handler = _SanitizedLoggingHandler(
                        logger_provider=cast(Any, CapturingProvider())
                    )
                    handler.emit(caplog.records[0])
            exported = emitted[0]
            assert exported.trace_id == original_context.trace_id
            assert exported.span_id == original_context.span_id
            assert exported.attributes["request_id"] == "original-request"
            assert exported.attributes["trace_id"] == format(
                original_context.trace_id, "032x"
            )
            assert (
                exported.attributes["code.function"]
                == "test_committed_record_preserves_original_trace_in_otlp"
            )
            assert len(emitted) == 1
        finally:
            reset_request_context(request_token)
            reset_request_session(session_token)
            provider.shutdown()


def test_domain_error_does_not_also_emit_http_failure(caplog):
    from app.observability import (
        bind_request_context,
        log_request_exception,
        reset_request_context,
    )

    request = Request({"type": "http", "method": "POST"})
    token = bind_request_context(request=request, request_id="failed-request")
    logger = get_logger("app.test")
    try:
        with caplog.at_level(logging.INFO):
            logger.error("feedback.issue.delivery_failed")
            log_request(
                logger, request=request, status_code=502, started_at=perf_counter()
            )
            log_request_exception(logger, request=request, started_at=perf_counter())
        assert [record.event for record in caplog.records] == [
            "feedback.issue.delivery_failed"
        ]
    finally:
        reset_request_context(token)


def test_unstructured_application_info_is_not_exported(caplog):
    with caplog.at_level(logging.INFO):
        get_logger("app.test").info("Routine diagnostic text")
    assert not DomainLogFilter().filter(caplog.records[0])


async def test_concurrent_http_domain_events_keep_their_request_context(caplog):
    import asyncio

    import httpx
    from fastapi import FastAPI
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.trace import TracerProvider

    from app.main import _install_request_context_middleware

    app = FastAPI()
    _install_request_context_middleware(app)
    provider = TracerProvider()
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    ready = asyncio.Event()
    arrived = 0

    @app.post("/feedback/{issue}")
    async def feedback(issue: str):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            ready.set()
        await ready.wait()
        get_logger("app.feedback").info(
            "feedback.issue.created", extra={"issue_identifier": issue}
        )
        return {"ok": True}

    try:
        with caplog.at_level(logging.INFO):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                responses = await asyncio.gather(
                    client.post(
                        "/feedback/IT-1", headers={"X-Request-ID": "request-1"}
                    ),
                    client.post(
                        "/feedback/IT-2", headers={"X-Request-ID": "request-2"}
                    ),
                )
        records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "feedback.issue.created"
        ]
        assert len(records) == 2
        for record in records:
            fields = record.event_data
            assert fields["request_id"] == "request-" + fields["issue_identifier"][-1]
            assert fields["route_template"] == "/feedback/{issue}"
            assert fields["http_method"] == "POST"
            assert len(fields["trace_id"]) == 32
            assert len(fields["span_id"]) == 16
            assert record.funcName == "feedback"
        assert records[0].event_data["trace_id"] != records[1].event_data["trace_id"]
        assert [r.headers["X-Request-ID"] for r in responses] == [
            "request-1",
            "request-2",
        ]
    finally:
        provider.shutdown()
