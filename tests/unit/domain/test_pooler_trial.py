import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.db.pooler_trial import build_trial_connector
from app.db.session import build_database_runtime


@pytest.fixture(autouse=True)
def enabled_flag(monkeypatch):
    monkeypatch.setattr("app.db.pooler_trial.build_percentage_provider", lambda _: AsyncMock(return_value=100))


def trial_settings(**kwargs):
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:secret@aws-1-eu-north-1.pooler.supabase.com:5432/postgres",
        database_transaction_pooler_enabled=True,
        **kwargs,
    )


async def test_trial_uses_transaction_port_and_preserves_identity(monkeypatch):
    connection = object()
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr("app.db.pooler_trial.asyncpg.connect", connect)
    assert await build_trial_connector(trial_settings())() is connection
    kwargs = connect.call_args.kwargs
    assert kwargs["port"] == 6543
    assert kwargs["host"] == "aws-1-eu-north-1.pooler.supabase.com"
    assert kwargs["user"] == "user"
    assert kwargs["password"] == "secret"
    assert kwargs["database"] == "postgres"
    assert kwargs["statement_cache_size"] == 0
    assert kwargs["timeout"] == 2


async def test_connection_failure_falls_back_and_cools_down(monkeypatch, caplog):
    connection = object()
    connect = AsyncMock(side_effect=[OSError("secret"), connection, connection, connection])
    monkeypatch.setattr("app.db.pooler_trial.asyncpg.connect", connect)
    clock = [100.0]
    monkeypatch.setattr("app.db.pooler_trial.time.monotonic", lambda: clock[0])
    connector = build_trial_connector(trial_settings())
    assert await connector() is connection
    assert await connector() is connection
    assert [c.kwargs["port"] for c in connect.call_args_list] == [6543, 5432, 5432]
    assert "secret" not in caplog.text
    clock[0] += 61
    assert await connector() is connection
    assert connect.call_args.kwargs["port"] == 6543


async def test_disabled_sampling_uses_fallback(monkeypatch):
    connect = AsyncMock()
    monkeypatch.setattr("app.db.pooler_trial.asyncpg.connect", connect)
    monkeypatch.setattr("app.db.pooler_trial.random.randrange", lambda _: 50)
    settings = trial_settings()
    monkeypatch.setattr("app.db.pooler_trial.build_percentage_provider", lambda _: AsyncMock(return_value=5))
    await build_trial_connector(settings)()
    assert connect.call_args.kwargs["port"] == 5432


async def test_cancelled_trial_does_not_fallback(monkeypatch):
    connect = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr("app.db.pooler_trial.asyncpg.connect", connect)
    with pytest.raises(asyncio.CancelledError):
        await build_trial_connector(trial_settings())()
    assert connect.await_count == 1


@pytest.mark.parametrize("url", [
    "sqlite+aiosqlite:///:memory:",
    "postgresql+asyncpg://example.test:5432/postgres",
    "postgresql+asyncpg://example.pooler.supabase.com:6543/postgres",
    "postgresql+asyncpg://example.pooler.supabase.com:5432/postgres?host=other.test",
])
def test_trial_refuses_incompatible_urls(url):
    settings = trial_settings()
    settings.database_url = url
    with pytest.raises(ValueError, match="session-pooler URL"):
        build_trial_connector(settings)


async def test_failed_fallback_propagates(monkeypatch):
    connect = AsyncMock(side_effect=[TimeoutError(), OSError("fallback unavailable")])
    monkeypatch.setattr("app.db.pooler_trial.asyncpg.connect", connect)
    with pytest.raises(OSError, match="fallback unavailable"):
        await build_trial_connector(trial_settings())()
    assert connect.await_count == 2


def test_trial_engine_uses_null_pool_and_disables_prepared_cache(monkeypatch):
    captured = {}
    def engine(url, **kwargs):
        captured.update(kwargs)
        return object()
    monkeypatch.setattr("app.db.session.create_async_engine", engine)
    monkeypatch.setattr("app.db.session.async_sessionmaker", lambda *a, **k: None)
    build_database_runtime(trial_settings())
    assert captured["poolclass"] is NullPool
    assert callable(captured["async_creator"])
    assert captured["connect_args"]["prepared_statement_cache_size"] == 0
    assert "pool_size" not in captured


def test_invalid_trial_configuration_preserves_fallback_engine(monkeypatch):
    captured = {}
    def engine(url, **kwargs):
        captured.update(kwargs)
        return object()
    monkeypatch.setattr("app.db.session.create_async_engine", engine)
    monkeypatch.setattr("app.db.session.async_sessionmaker", lambda *a, **k: None)
    settings = trial_settings()
    settings.database_url = "postgresql+asyncpg://example.test/postgres"
    build_database_runtime(settings)
    assert "async_creator" not in captured
    assert captured["poolclass"] is NullPool
