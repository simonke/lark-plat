from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

WEAK_SECRET_KEYS = {"change-me-to-a-long-random-string", "change-me-32-bytes-random-key", ""}


class Settings(BaseSettings):
    """Central application settings. Values loaded from env / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "lark-plat"
    app_env: str = "dev"
    debug: bool = True
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    secret_key: str = "change-me-to-a-long-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    refresh_token_expire_days: int = 7

    credential_encrypt_key: str = "change-me-32-bytes-random-key"

    database_url: str = "postgresql+psycopg2://lark:lark@localhost:5432/lark_plat"
    redis_url: str = "redis://localhost:6379/0"

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    exec_global_concurrency: int = 50
    exec_host_concurrency: int = 5
    exec_batch_threshold: int = 50

    cors_origins: list[str] = ["http://localhost:5173"]

    audit_append_only: bool = True
    login_max_failures: int = 5
    login_lock_minutes: int = 10

    # Agent heartbeat/offline
    agent_heartbeat_timeout_sec: int = 90
    agent_heartbeat_interval_sec: int = 30

    # Bootstrap admin for seed (env-only; prod requires an explicit value)
    seed_admin_password: str = ""

    @model_validator(mode="after")
    def _fail_fast_on_weak_secrets(self) -> Self:
        if self.app_env == "prod":
            if self.secret_key in WEAK_SECRET_KEYS or len(self.secret_key) < 32:
                raise ValueError(
                    "SECRET_KEY must be set via env (>=32 chars, not the default) in prod"
                )
            if self.credential_encrypt_key in WEAK_SECRET_KEYS or len(self.credential_encrypt_key) < 16:
                raise ValueError(
                    "CREDENTIAL_ENCRYPT_KEY must be set via env (>=16 chars, not the default) in prod"
                )
        return self


settings = Settings()
