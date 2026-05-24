from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class _EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class AuthSettings(_EnvSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_")
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"


class AppSettings(_EnvSettings):
    model_config = SettingsConfigDict(env_prefix="APP_")
    name: str = "schedulerlm"
    debug: bool = False


class LogSettings(_EnvSettings):
    model_config = SettingsConfigDict(env_prefix="LOG_")
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: str = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


class DatabaseSettings(_EnvSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")
    host: str = "localhost"
    port: int = 5432
    user: str
    password: SecretStr
    name: str
    min_pool_size: int = 1
    max_pool_size: int = 10
    connect_timeout: float = 10.0
    connect_retries: int = 3
    connect_retry_delay: float = 1.0

    @property
    def async_url(self) -> str:
        pwd = self.password.get_secret_value()
        return f"postgresql+asyncpg://{self.user}:{pwd}@{self.host}:{self.port}/{self.name}"


class SchedulerSettings(_EnvSettings):
    model_config = SettingsConfigDict(env_prefix="SCHEDULER_")
    webhook_jwt_ttl_minutes: int = 5
    webhook_timeout_seconds: float = 30.0
    scheduler_id: str | None = None


class Settings(_EnvSettings):
    model_config = SettingsConfigDict(frozen=True)
    app: AppSettings = Field(default_factory=AppSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    log: LogSettings = Field(default_factory=LogSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()
