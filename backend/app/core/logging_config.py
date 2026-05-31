"""Structured logging configuration with request ID tracing.

Uses structlog for JSON-structured logs with automatic request_id injection
via FastAPI middleware. This enables:
1. Log correlation — trace all logs for a single HTTP request
2. JSON output — machine-parseable logs for ELK/Datadog
3. Dev-friendly console output — colored, readable during development

Usage:
    from app.core.logging_config import get_logger
    logger = get_logger("my_module")
    logger.info("task_completed", duration_ms=150, agent_id="agent_pm")

Output (production JSON):
    {"event":"task_completed","duration_ms":150,"agent_id":"agent_pm",
     "request_id":"abc123","logger":"my_module","level":"info","timestamp":"..."}

Output (development console):
    [info] (abc123) task_completed  duration_ms=150 agent_id=agent_pm
"""
import os
import sys
import logging
import uuid
from contextvars import ContextVar

# Context variable to store request_id per async task
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Get the current request ID from context."""
    return _request_id_ctx.get()


def set_request_id(request_id: str = None) -> str:
    """Set the request ID in context. Generates a new one if not provided."""
    rid = request_id or uuid.uuid4().hex[:12]
    _request_id_ctx.set(rid)
    return rid


def _is_structlog_available() -> bool:
    """Check if structlog is installed."""
    try:
        import structlog  # noqa: F401
        return True
    except ImportError:
        return False


def setup_logging():
    """Configure structured logging for the application.

    If structlog is available, configures JSON output in production
    and colored console output in development.
    Falls back to standard logging if structlog is not installed.
    """
    if not _is_structlog_available():
        # Fallback: configure standard logging with request_id format
        log_format = "%(asctime)s [%(levelname)s] (%(request_id)s) %(name)s: %(message)s"
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            datefmt="%H:%M:%S",
        )
        # Add filter to inject request_id into standard log records
        for handler in logging.root.handlers:
            handler.addFilter(_RequestIdFilter())
        return

    import structlog

    env = os.environ.get("AGENTHUB_ENV", "development")

    # Shared processors for all loggers
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _inject_request_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if env == "production":
        # JSON output for production (ELK, Datadog, etc.)
        renderer = structlog.processors.JSONRenderer()
    else:
        # Colored console output for development
        renderer = structlog.dev.ConsoleRenderer(
            colors=True,
        )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging to use structlog formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


class _RequestIdFilter(logging.Filter):
    """Standard logging filter that injects request_id from ContextVar."""

    def filter(self, record):
        record.request_id = get_request_id()
        return True


def _inject_request_id(logger, method_name, event_dict):
    """structlog processor to inject request_id from ContextVar."""
    event_dict["request_id"] = get_request_id()
    return event_dict


def get_logger(name: str = "app"):
    """Get a structured logger instance.

    Returns a structlog BoundLogger if available, otherwise a standard logger.
    """
    if _is_structlog_available():
        import structlog
        return structlog.get_logger(name)
    else:
        logger = logging.getLogger(name)
        if not any(isinstance(f, _RequestIdFilter) for f in logger.filters):
            logger.addFilter(_RequestIdFilter())
        return logger


# ---- FastAPI Middleware ----

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIdMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that assigns a unique request_id to every HTTP request
    and injects it into the logging context for log correlation.
    """

    async def dispatch(self, request: Request, call_next):
        # Use X-Request-ID header if provided (e.g. from load balancer), else generate
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        set_request_id(request_id)

        # Also set structlog contextvars if available
        if _is_structlog_available():
            import structlog
            structlog.contextvars.clear_contextvars()
            structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
