from pydantic_settings import BaseSettings, SettingsConfigDict


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


settings = Settings()
