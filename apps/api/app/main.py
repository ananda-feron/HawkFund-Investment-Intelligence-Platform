import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.observability import (
    RequestLoggingMiddleware,
    configure_logging,
    request_id_context,
)

settings = get_settings()
configure_logging(settings.log_level, settings.service_name, settings.release)
logger = logging.getLogger("hawkfund.api")
app = FastAPI(
    title="HawkFundOS API",
    version="0.1.0",
    docs_url=None if settings.app_env == "production" else "/docs",
    redoc_url=None if settings.app_env == "production" else "/redoc",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, error: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "-")
    token = request_id_context.set(request_id)
    logger.exception("unhandled_request_error", extra={"path": request.url.path})
    request_id_context.reset(token)
    response = JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "Internal server error"}},
    )
    response.headers["x-request-id"] = request_id
    return response


@app.get("/health/live", tags=["health"])
def live() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name, "release": settings.release}


@app.get("/health/ready", tags=["health"])
def ready() -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["postgresql"] = "ok"
    except Exception:
        logger.warning("readiness_dependency_failed", extra={"dependency": "postgresql"})
        checks["postgresql"] = "unavailable"
    try:
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        redis.ping()
        checks["redis"] = "ok"
    except Exception:
        logger.warning("readiness_dependency_failed", extra={"dependency": "redis"})
        checks["redis"] = "unavailable"
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ready" if healthy else "not_ready", "checks": checks},
    )
