import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_requires_tls_hosts_and_release() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(app_env="production")

    message = str(error.value)
    assert "WEB_ORIGIN must use HTTPS" in message
    assert "DATABASE_URL must require TLS" in message
    assert "REDIS_URL must use TLS" in message
    assert "RELEASE must identify an immutable deployment" in message


def test_secure_production_configuration_is_accepted() -> None:
    settings = Settings(
        app_env="production",
        web_origin="https://hawkfund.example.edu",
        database_url="postgresql+psycopg://app:secret@db/hawkfund?sslmode=require",
        redis_url="rediss://:secret@cache:6379/0",
        allowed_hosts="api.hawkfund.example.edu",
        release="sha-abc123",
    )

    assert settings.allowed_host_list == ["api.hawkfund.example.edu"]
