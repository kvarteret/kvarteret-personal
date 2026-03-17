from app.config import Settings
from app.config import validate_production_secrets


def test_settings_strip_boolean_whitespace() -> None:
    settings = Settings.model_validate({"review_bypass_enabled": "false\n"})

    assert settings.review_bypass_enabled is False


def test_settings_strip_string_whitespace() -> None:
    settings = Settings.model_validate(
        {
            "app_public_base_url": " https://example.com/ \n",
            "photo_bucket": " personnel-photos \n",
        }
    )

    assert settings.app_public_base_url == "https://example.com/"
    assert settings.photo_bucket == "personnel-photos"


def test_validate_production_secrets_rejects_default_secret() -> None:
    settings = Settings(app_env="production", app_secret_key="change-me")

    try:
        validate_production_secrets(settings)
    except ValueError as exc:
        assert str(exc) == "APP_SECRET_KEY must be set to a non-default value in production."
    else:
        raise AssertionError("Expected production secret validation to fail.")
