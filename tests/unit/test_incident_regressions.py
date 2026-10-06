import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.groups.service import GroupsService
from app.error_tracking import (
    ExceptionLoggingHandler,
    begin_error_tracking_request,
    end_error_tracking_request,
    sanitize_exception_event,
)
from app.exception_diagnostics import exception_diagnostics
from app.infrastructure.email.resend import ResendDeliveryError
from app.main import (
    _install_auth_context_middleware,
    _install_request_context_middleware,
)


@pytest.mark.parametrize("points", [2**31, -(2**31) - 1])
async def test_group_role_overflow_is_rejected_before_database_access(points):
    # No session exists: accessing SQL would fail before this expected ValueError.
    service = object.__new__(GroupsService)
    with pytest.raises(ValueError, match="Pingvinpoeng"):
        await service.update_group_role(7, 14, role_name="Role", pingvin_points=points)
    with pytest.raises(ValueError, match="Pingvinpoeng"):
        await service.create_group_role(7, role_name="Role", pingvin_points=points)


def test_database_diagnostics_keep_sqlstate_but_no_query_or_message():
    class DatabaseError(Exception):
        sqlstate = "08006"

    error = DatabaseError("password=secret SQL with private values")
    fields = exception_diagnostics(error)
    assert fields["db_sqlstate"] == "08006"
    assert "secret" not in json.dumps(fields)
    event = sanitize_exception_event(
        {"event": "$exception", "properties": {**fields, "password": "secret"}}
    )
    assert event["properties"]["db_sqlstate"] == "08006"
    assert "secret" not in json.dumps(event)


def test_exception_chain_is_captured_once_per_request_but_next_request_still_reports():
    captures = []
    client = SimpleNamespace(
        capture_exception=lambda *args, **kwargs: captures.append((args, kwargs))
    )
    handler = ExceptionLoggingHandler(client, Settings(_env_file=None, app_env="test"))
    root = ResendDeliveryError("resend_connection", retryable=True, delivery_uncertain=True)
    wrapper = RuntimeError("private")
    wrapper.__cause__ = root
    for _ in range(2):
        token = begin_error_tracking_request()
        try:
            for error in (root, wrapper):
                handler.emit(
                    logging.LogRecord(
                        "app.example",
                        logging.ERROR,
                        __file__,
                        1,
                        "failed",
                        (),
                        (type(error), error, None),
                    )
                )
        finally:
            end_error_tracking_request(token)
    assert len(captures) == 2
    assert captures[0][1]["properties"]["delivery_uncertain"] is True


@pytest.mark.parametrize("path", ["/protected", "/api/protected"])
def test_auth_database_failure_returns_temporary_unavailable_instead_of_login(path):
    class Store:
        async def load_authenticated_user(self, session_id):
            raise ConnectionError("private database credentials")

    container = SimpleNamespace(
        settings=SimpleNamespace(session_cookie_name="session"),
        session_cookie_signer=SimpleNamespace(unsign_session_id=lambda cookie: cookie),
        session_store=Store(),
    )
    app = FastAPI()
    _install_auth_context_middleware(app, container)
    _install_request_context_middleware(app)

    @app.get(path)
    def protected():
        pytest.fail("must not continue with a broken database")

    client = TestClient(app)
    client.cookies.set("session", "valid-cookie")
    response = client.get(path)
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert response.headers["X-Request-ID"]
    assert "private" not in response.text
