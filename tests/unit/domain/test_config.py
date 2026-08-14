from app.config import Settings
from app.config import validate_production_secrets
from app.db.session import build_database_runtime
from app.db.session import NullPool


def test_validate_production_secrets_requires_explicit_app_env() -> None:
    settings = Settings(app_env=None)

    try:
        validate_production_secrets(settings)
    except ValueError as exc:
        assert str(exc) == (
            "APP_ENV must be explicitly set to development, test, or production."
        )
    else:
        raise AssertionError("Expected missing APP_ENV validation to fail.")


def test_settings_strip_boolean_whitespace() -> None:
    settings = Settings.model_validate({"review_bypass_enabled": "false\n"})

    assert settings.review_bypass_enabled is False


def test_settings_strip_string_whitespace() -> None:
    settings = Settings.model_validate(
        {
            "app_public_base_url": " https://example.com/ \n",
            "azure_photo_container": " images \n",
        }
    )

    assert settings.app_public_base_url == "https://example.com/"
    assert settings.azure_photo_container == "images"


def test_validate_production_secrets_rejects_default_secret() -> None:
    settings = Settings(app_env="production", app_secret_key="change-me")

    try:
        validate_production_secrets(settings)
    except ValueError as exc:
        assert str(exc) == (
            "APP_SECRET_KEY must be a non-default value of at least 32 characters "
            "in production."
        )
    else:
        raise AssertionError("Expected production secret validation to fail.")


def test_validate_production_secrets_rejects_missing_public_base_url() -> None:
    settings = Settings(
        app_env="production",
        app_secret_key="a-production-secret-with-32-characters",
        app_public_base_url=None,
        email_dispatch_enabled=False,
    )

    try:
        validate_production_secrets(settings)
    except ValueError as exc:
        assert str(exc) == "APP_PUBLIC_BASE_URL is required in production."
    else:
        raise AssertionError("Expected production public URL validation to fail.")


def test_validate_production_secrets_rejects_insecure_public_base_url() -> None:
    settings = Settings(
        app_env="production",
        app_secret_key="a-production-secret-with-32-characters",
        app_public_base_url="http://personal.example.test/app",
        email_dispatch_enabled=False,
    )

    try:
        validate_production_secrets(settings)
    except ValueError as exc:
        assert str(exc) == (
            "APP_PUBLIC_BASE_URL must be an HTTPS origin without credentials, a path, "
            "query, or fragment in production."
        )
    else:
        raise AssertionError("Expected production public URL validation to fail.")


def test_validate_production_secrets_accepts_complete_production_settings() -> None:
    settings = Settings(
        app_env="production",
        app_secret_key="a-production-secret-with-32-characters",
        app_public_base_url="https://personal.example.test",
        email_dispatch_enabled=False,
    )

    assert validate_production_secrets(settings) is settings


def test_build_database_runtime_uses_queue_pool_by_default(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_async_engine(database_url: str, **kwargs):
        captured["database_url"] = database_url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("app.db.session.create_async_engine", fake_create_async_engine)
    monkeypatch.setattr("app.db.session.async_sessionmaker", lambda engine, expire_on_commit: ("session-factory", engine, expire_on_commit))

    runtime = build_database_runtime(Settings(database_url="postgresql+asyncpg://example.test/postgres"))

    assert runtime.engine is not None
    assert captured["database_url"] == "postgresql+asyncpg://example.test/postgres"
    assert captured["kwargs"] == {
        "connect_args": {},
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 5,
        "pool_timeout": 10,
        "pool_recycle": 1800,
        "pool_use_lifo": True,
    }


def test_build_database_runtime_uses_null_pool_on_vercel(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_async_engine(database_url: str, **kwargs):
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("app.db.session.create_async_engine", fake_create_async_engine)
    monkeypatch.setattr("app.db.session.async_sessionmaker", lambda engine, expire_on_commit: ("session-factory", engine, expire_on_commit))
    monkeypatch.setenv("VERCEL", "1")

    build_database_runtime(Settings(database_url="postgresql+asyncpg://example.test/postgres"))

    assert captured["kwargs"] == {
        "connect_args": {},
        "pool_pre_ping": True,
        "poolclass": NullPool,
    }


def test_build_database_runtime_allows_null_pool_override(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_async_engine(database_url: str, **kwargs):
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("app.db.session.create_async_engine", fake_create_async_engine)
    monkeypatch.setattr("app.db.session.async_sessionmaker", lambda engine, expire_on_commit: ("session-factory", engine, expire_on_commit))

    build_database_runtime(
        Settings(
            database_url="postgresql+asyncpg://example.test/postgres",
            database_use_null_pool=True,
        )
    )

    assert captured["kwargs"] == {
        "connect_args": {},
        "pool_pre_ping": True,
        "poolclass": NullPool,
    }
