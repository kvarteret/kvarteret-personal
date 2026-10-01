from __future__ import annotations

import logging
from time import perf_counter

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.db.session import reset_request_session, set_request_session
from app.observability import emit_committed_event, log_operation_timing, log_request
from app.telemetry import DomainLogFilter


@pytest.mark.parametrize("status", [200, 202, 303, 400, 401, 404, 422, 429])
def test_routine_http_responses_are_debug_only(caplog, status):
    logger = logging.getLogger("app.test")
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
            logging.getLogger("app.test"),
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
            logging.getLogger("app.performance"),
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
                emit_committed_event(
                    logging.getLogger("app.audit"),
                    "admin.activity",
                    fields={"subject_id": 42, "action": "volunteer.delete"},
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
                emit_committed_event(logging.getLogger("app.audit"), "admin.activity")
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
                emit_committed_event(
                    logging.getLogger("app.audit"),
                    "admin.activity",
                    fields={"subject_id": 1},
                )
                nested = await session.begin_nested()
                emit_committed_event(
                    logging.getLogger("app.audit"),
                    "admin.activity",
                    fields={"subject_id": 2},
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


async def test_closed_transaction_does_not_leak_into_reused_session(caplog):
    async with AsyncSession() as session:
        token = set_request_session(session)
        try:
            with caplog.at_level(logging.INFO):
                await session.begin()
                emit_committed_event(logging.getLogger("app.audit"), "admin.activity")
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
