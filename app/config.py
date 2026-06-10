from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development")
    app_secret_key: str = Field(default="change-me")
    app_public_base_url: str | None = Field(default=None)
    supabase_url: str | None = Field(default=None)
    supabase_secret_key: str | None = Field(default=None)
    azure_blob_connection_string: str | None = Field(default=None)
    azure_blob_account_name: str | None = Field(default=None)
    azure_blob_account_key: str | None = Field(default=None)
    azure_photo_container: str = Field(default="images")
    photo_upload_max_bytes: int = Field(default=40 * 1024 * 1024)
    photo_max_dimension: int = Field(default=2048)
    photo_default_size: int = Field(default=512)
    database_url: str | None = Field(default=None)
    database_use_null_pool: bool = Field(default=False)
    database_pool_size: int = Field(default=5)
    database_max_overflow: int = Field(default=5)
    database_pool_timeout_seconds: int = Field(default=10)
    database_pool_recycle_seconds: int = Field(default=1800)
    # Linear feedback integration — all products route through this backend
    linear_api_key: str | None = Field(default=None)
    linear_team_id: str | None = Field(default=None)
    linear_project_id_personal: str | None = Field(default=None)
    linear_project_id_internbevis: str | None = Field(default=None)
    linear_project_id_nettside: str | None = Field(default=None)
    linear_state_id_triage: str | None = Field(default=None)
    # slack_feedback_webhook_url: str | None = Field(default=None)
    smtp_server: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SMTP_SERVER", "EMAIL_SERVER", "Email__Server"),
    )
    smtp_port: int = Field(
        default=587,
        validation_alias=AliasChoices("SMTP_PORT", "EMAIL_PORT", "Email__Port"),
    )
    smtp_sender_name: str | None = Field(
        default="Det Akademiske Kvarter",
        validation_alias=AliasChoices(
            "SMTP_SENDER_NAME", "EMAIL_SENDER_NAME", "Email__SenderName"
        ),
    )
    smtp_sender_email: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SMTP_SENDER_EMAIL", "EMAIL_SENDER_EMAIL", "Email__SenderEmail"
        ),
    )
    smtp_account: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SMTP_ACCOUNT", "EMAIL_ACCOUNT", "Email__Account"
        ),
    )
    smtp_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SMTP_PASSWORD", "EMAIL_PASSWORD", "Email__Password"
        ),
    )
    smtp_use_starttls: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "SMTP_USE_STARTTLS", "EMAIL_USE_STARTTLS", "Email__UseStartTls"
        ),
    )
    spotify_client_id: str | None = Field(default=None)
    spotify_client_secret: str | None = Field(default=None)
    spotify_refresh_token: str | None = Field(default=None)
    now_playing_cache_seconds: float = Field(default=10.0)
    now_playing_stale_grace_seconds: float = Field(default=30.0)
    review_bypass_enabled: bool = Field(default=False)
    review_bypass_email: str | None = Field(default=None)
    review_bypass_token: str | None = Field(default=None)
    log_level: str = Field(default="INFO")
    session_cookie_name: str = Field(default="kvarteret_session")
    session_ttl_hours: int = Field(default=12)
    session_cache_ttl_seconds: int = Field(default=300)
    login_attempt_limit: int = Field(default=10)
    login_attempt_window_seconds: int = Field(default=900)
    pending_volunteer_applications_cache_ttl_seconds: int = Field(default=30)
    volunteer_detail_cache_ttl_seconds: int = Field(default=300)
    admin_accounts_cache_ttl_seconds: int = Field(default=60)
    mobile_card_access_code_ttl_minutes: int = Field(default=10)
    mobile_card_access_code_request_limit: int = Field(default=5)
    mobile_card_access_code_request_window_seconds: int = Field(default=300)
    mobile_card_session_attempt_limit: int = Field(default=5)
    mobile_card_session_attempt_window_seconds: int = Field(default=600)
    mobile_card_session_ttl_days: int = Field(default=90)
    mobile_card_session_renewal_threshold_days: int = Field(default=30)

    @field_validator(
        "app_env",
        "app_secret_key",
        "app_public_base_url",
        "supabase_url",
        "supabase_secret_key",
        "azure_blob_connection_string",
        "azure_blob_account_name",
        "azure_blob_account_key",
        "azure_photo_container",
        "database_url",
        "linear_api_key",
        "linear_team_id",
        "linear_project_id_personal",
        "linear_project_id_internbevis",
        "linear_project_id_nettside",
        "linear_state_id_triage",
        "smtp_server",
        "smtp_sender_name",
        "smtp_sender_email",
        "smtp_account",
        "smtp_password",
        "spotify_client_id",
        "spotify_client_secret",
        "spotify_refresh_token",
        "review_bypass_email",
        "review_bypass_token",
        "log_level",
        "session_cookie_name",
        mode="before",
    )
    @classmethod
    def strip_string_settings(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None if value is not None else value
        return value

    @field_validator("review_bypass_enabled", mode="before")
    @classmethod
    def strip_boolean_settings(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


def validate_production_secrets(settings: Settings) -> Settings:
    if settings.app_env == "production" and settings.app_secret_key == "change-me":
        msg = "APP_SECRET_KEY must be set to a non-default value in production."
        raise ValueError(msg)
    return settings


def get_settings() -> Settings:
    return validate_production_secrets(Settings())
