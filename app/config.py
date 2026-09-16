from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # local = SQLite + in-process queue (no Docker, no Redis, no RabbitMQ)
    # broker = Postgres + Redis + RabbitMQ
    mode: str = "local"
    database_url: str = "sqlite+aiosqlite:///./notify.db"
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    api_key: str = "dev-key"
    provider_fail_rate: float = 0.0
    retry_delays_seconds: str = "2,5,10"
    max_attempts: int = 5
    log_level: str = "INFO"
    marketing_per_user_per_day: int = 10
    provider_rps: int = 200

    @property
    def is_local(self) -> bool:
        return self.mode.lower() != "broker"

    @property
    def retry_delays(self) -> list:
        return [int(x.strip()) for x in self.retry_delays_seconds.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
