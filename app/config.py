"""Application configuration loaded from environment variables.

Uses pydantic-settings so values can come from a .env file or the
process environment. Defaults are sensible for local development.
"""
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./mandlzi.db"

    # JWT / Auth
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_MINUTES: int = 60

    # Business rules (global defaults; policies may override)
    GRACE_PERIOD_DAYS: int = 30
    LAPSE_THRESHOLD_MONTHS: int = 3

    # Field-capture app
    PHOTO_STORAGE_BACKEND: str = "filesystem"   # "filesystem" | "s3" (s3 placeholder for now)
    PHOTO_STORAGE_PATH: str = "./media"         # root for the filesystem adapter
    DEVICE_JWT_EXPIRES_DAYS: int = 180
    ENROLLMENT_CODE_EXPIRES_HOURS: int = 24
    DEV_FIELD_ADMIN_NO_LOGIN: bool = True

    # App
    APP_NAME: str = "Mandlzi Subscription Management"
    DEBUG: bool = True
    # Set to True in production. Triggers stricter boot-time checks
    # (e.g. refuse to start with the default JWT_SECRET).
    PRODUCTION: bool = False

    # Rate limiting (slowapi). Disabled in unit/integration tests via
    # `RATE_LIMIT_ENABLED=0` so test suites stay deterministic.
    RATE_LIMIT_ENABLED: bool = True
    # The actual limit strings (e.g. "5/minute") for the auth endpoints.
    # Tweak via env if you need different defaults in different envs.
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_REGISTER: str = "5/minute"

    # Observability: structured request logging + Prometheus /metrics.
    # Disable in unit tests so they don't churn the global registry or
    # spam stdout. Keep ON in production.
    REQUEST_LOG_ENABLED: bool = True
    METRICS_ENABLED: bool = True
    # /metrics returns Prometheus text; if you want it behind auth, set
    # this to True and `require_admin` will guard it.
    METRICS_REQUIRE_ADMIN: bool = False

    # If True, the app will call `Base.metadata.create_all` on startup. This
    # is convenient for local SQLite dev but should be OFF in production -
    # `alembic upgrade head` is the source of truth there.
    RUN_INIT_DB: bool = True

    # Background scheduler: enable APScheduler to run the daily billing
    # sweep (re-evaluate policies, auto-lapse, notify missed payments).
    # Disable in test runs or when running multiple replicas without a
    # shared lock (otherwise the sweep would run N times).
    SCHEDULER_ENABLED: bool = True
    SWEEP_HOUR_UTC: int = 2     # cron hour for the daily sweep
    SWEEP_MINUTE_UTC: int = 0

    # Notification dispatcher: turn unsent Notification rows into real
    # outbound messages. "log" just logs them (default); "webhook" POSTs
    # JSON to NOTIFICATION_WEBHOOK_URL.
    NOTIFICATION_PROVIDER: str = "log"
    NOTIFICATION_WEBHOOK_URL: str = ""
    NOTIFICATION_EMAIL_PROVIDER: str = "log"  # "log" | "smtp"
    NOTIFICATION_EMAIL_FROM: str = "noreply@mandlzi.local"
    NOTIFICATION_SMTP_HOST: str = "localhost"
    NOTIFICATION_SMTP_PORT: int = 25
    NOTIFICATION_SMTP_USERNAME: str = ""
    NOTIFICATION_SMTP_PASSWORD: str = ""
    NOTIFICATION_SMTP_STARTTLS: bool = False
    NOTIFICATION_DISPATCH_INTERVAL_MINUTES: int = 5
    NOTIFICATION_MAX_ATTEMPTS: int = 5

    # Optional S3-compatible storage for field-capture photos.
    PHOTO_STORAGE_S3_BUCKET: str = ""
    PHOTO_STORAGE_S3_PREFIX: str = "id_photos"
    PHOTO_STORAGE_S3_REGION: str = ""
    PHOTO_STORAGE_S3_ENDPOINT_URL: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("DEBUG", mode="before")
    @classmethod
    def _parse_debug_mode(cls, value):
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == "release":
                return False
            if lowered == "debug":
                return True
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
