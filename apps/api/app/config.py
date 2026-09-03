from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://hawkfund:hawkfund@localhost:5432/hawkfund"
    redis_url: str = "redis://localhost:6379/0"
    web_origin: str = "http://localhost:3000"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    service_name: str = "hawkfund-api"
    release: str = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_host_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]

    @model_validator(mode="after")
    def production_invariants(self) -> "Settings":
        if self.app_env != "production":
            return self
        errors: list[str] = []
        if not self.web_origin.startswith("https://"):
            errors.append("WEB_ORIGIN must use HTTPS")
        if "sslmode=require" not in self.database_url:
            errors.append("DATABASE_URL must require TLS")
        if not self.redis_url.startswith("rediss://"):
            errors.append("REDIS_URL must use TLS")
        if not self.allowed_host_list or "*" in self.allowed_host_list:
            errors.append("ALLOWED_HOSTS must be an explicit non-empty allowlist")
        if self.release == "development":
            errors.append("RELEASE must identify an immutable deployment")
        if errors:
            raise ValueError("; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
