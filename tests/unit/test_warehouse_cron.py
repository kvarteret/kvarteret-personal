from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.internal.router import get_settings, router


@pytest.mark.parametrize("secret,authorization", [
    (None, None), ("cron-test", None), ("cron-test", "Bearer wrong"),
])
def test_cron_rejects_unauthorized_before_accessing_database(
    monkeypatch, secret, authorization
):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(cron_secret=secret)
    refresh = AsyncMock()
    monkeypatch.setattr("app.internal.router.refresh_counts", refresh)
    response = TestClient(app).get(
        "/internal/cron/refresh-warehouse-volunteer-counts",
        headers={"Authorization": authorization} if authorization else {},
    )
    assert response.status_code == 401
    refresh.assert_not_called()


def test_cron_refreshes_with_existing_secret(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(cron_secret="cron-test")
    session = object()
    monkeypatch.setattr("app.internal.router.current_session", lambda: session)
    refresh = AsyncMock(return_value=8)
    monkeypatch.setattr("app.internal.router.refresh_counts", refresh)
    response = TestClient(app).get(
        "/internal/cron/refresh-warehouse-volunteer-counts",
        headers={"Authorization": "Bearer cron-test"},
    )
    assert response.status_code == 200
    assert response.json() == {"refreshed_rows": 8}
    refresh.assert_awaited_once_with(session)
    assert "/internal/cron/refresh-warehouse-volunteer-counts" not in app.openapi()["paths"]
