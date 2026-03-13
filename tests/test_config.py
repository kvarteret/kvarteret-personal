from app.config import Settings


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
